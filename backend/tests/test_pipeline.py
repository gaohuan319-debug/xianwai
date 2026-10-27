"""端到端测试：mock 语音识别 + 假的大模型，跑通 上传 → 转写 → 分析 → 待办/洞察。"""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("XW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("XW_ASR_ENGINE", "mock")
    monkeypatch.setenv("XW_LLM_API_KEY", "test")

    import app.config

    importlib.reload(app.config)
    for mod in ("app.db", "app.llm", "app.analyzers", "app.pipeline", "app.main"):
        importlib.reload(importlib.import_module(mod))

    from fastapi.testclient import TestClient

    import app.llm
    import app.main

    def fake_chat_json(system: str, user: str) -> dict:
        if '"todos"' in user:
            return {"todos": [{"title": "明天上午陪妈妈去银行", "owner": "我", "due": "明天上午",
                               "confidence": 0.9, "evidence": [7, 99]}]}
        if '"insights"' in user:
            return {"insights": [{"title": "疑似冒充银行客服诈骗", "detail": "安全账户、要求保密",
                                  "level": "warning", "confidence": 1.7, "evidence": ["#3", 5]}]}
        return {"title": "妈妈接到诈骗电话", "summary": "下班后和妈妈通话。", "highlights": []}

    monkeypatch.setattr(app.llm, "chat_json", fake_chat_json)
    with TestClient(app.main.app) as c:
        yield c


def test_upload_and_analyze(client):
    res = client.post("/api/recordings", files={"file": ("a.webm", b"fake-audio", "audio/webm")})
    assert res.status_code == 200
    rec_id = res.json()["id"]

    # TestClient 会在响应返回前执行完后台任务
    rec = client.get(f"/api/recordings/{rec_id}").json()
    assert rec["status"] == "done", rec["error"]
    assert rec["title"] == "妈妈接到诈骗电话"
    assert len(rec["segments"]) == 9
    assert [s["speaker"] for s in rec["speakers"]] == ["S1", "S2"]

    warnings = [i for i in rec["insights"] if i["kind"] == "insight"]
    assert warnings and all(w["level"] == "warning" for w in warnings)
    assert warnings[0]["evidence"] == [3, 5]  # "#3" 被解析为 3
    assert warnings[0]["confidence"] == 1.0  # 超范围被截断

    [todo] = rec["todos"]
    assert todo["evidence"] == [7]  # 不存在的片段 99 被丢弃

    # 勾选完成后重新分析，不应重复生成这条待办
    client.patch(f"/api/todos/{todo['id']}", json={"done": True})
    client.post(f"/api/recordings/{rec_id}/analyze")
    todos = client.get("/api/todos").json()
    assert len(todos) == 1 and todos[0]["done"] == 1


def test_name_speaker_shows_in_transcript(client):
    rec_id = client.post("/api/recordings", files={"file": ("a.m4a", b"x", "audio/mp4")}).json()["id"]
    res = client.put(f"/api/recordings/{rec_id}/speakers/S2", json={"name": "妈妈"})
    assert res.json()["name"] == "妈妈"

    from app.pipeline import build_transcript

    transcript, _ = build_transcript(rec_id)
    assert "妈妈：哎，今天下午" in transcript
    assert client.get("/api/people").json()[0]["name"] == "妈妈"


def test_builtin_analyzers_load(client):
    ids = {a["id"] for a in client.get("/api/analyzers").json()}
    assert {"diary", "todo", "anti_fraud", "communication"} <= ids


def test_parse_json_tolerates_fences():
    from app.llm import parse_json

    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('好的，结果如下：{"a": [1, 2]} 希望有帮助') == {"a": [1, 2]}
    assert parse_json('{"a": [{"t": "x"},\n  ],\n "b": 1,\n}') == {"a": [{"t": "x"}], "b": 1}
    assert json.dumps(parse_json('{"x": "中文"}'), ensure_ascii=False) == '{"x": "中文"}'


def test_retranscribe_with_speaker_count(client):
    rec_id = client.post("/api/recordings", files={"file": ("a.m4a", b"x", "audio/mp4")},
                         data={"num_speakers": "2"}).json()["id"]
    assert client.get(f"/api/recordings/{rec_id}").json()["num_speakers"] == 2
    client.put(f"/api/recordings/{rec_id}/speakers/S2", json={"name": "妈妈"})

    assert client.post(f"/api/recordings/{rec_id}/transcribe", json={"num_speakers": 11}).status_code == 400
    assert client.post(f"/api/recordings/{rec_id}/transcribe", json={"num_speakers": 1}).status_code == 200
    rec = client.get(f"/api/recordings/{rec_id}").json()
    assert rec["status"] == "done" and rec["num_speakers"] == 1
    assert all(s["name"] is None for s in rec["speakers"])  # 旧标注已清空


def test_chat_json_retries_transient_errors(monkeypatch):
    import httpx

    import app.llm as llm

    monkeypatch.setattr(llm.settings, "llm_api_key", "test")
    monkeypatch.setattr(llm, "RETRY_BACKOFF", 0)
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        req = httpx.Request("POST", url)
        if len(calls) == 1:
            raise httpx.ConnectError("Temporary failure in name resolution", request=req)
        if len(calls) == 2:
            return httpx.Response(503, request=req, text="busy")
        return httpx.Response(200, request=req, json={"choices": [{"message": {"content": '{"ok": 1}'}}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert llm.chat_json("s", "u") == {"ok": 1}
    assert len(calls) == 3

    # 401 这类客户端错误不重试
    calls.clear()
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: (calls.append(url), httpx.Response(401, request=httpx.Request("POST", url), text="bad key"))[1])
    with pytest.raises(llm.LLMError, match="401"):
        llm.chat_json("s", "u")
    assert len(calls) == 1
