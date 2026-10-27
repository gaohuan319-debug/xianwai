from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, analyzers, audio, llm, pipeline, rules
from .analyzers import KINDS, MAX_PROMPT_CHARS, Analyzer
from .config import settings
from .db import connect, init_db, row_to_dict, rows_to_dicts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="弦外 Xianwai", version=__version__)
init_db()


def _get_recording(rec_id: str) -> dict:
    with connect() as conn:
        rec = row_to_dict(conn.execute("SELECT * FROM recordings WHERE id = ?", (rec_id,)).fetchone())
    if rec is None:
        raise HTTPException(404, "录音不存在")
    return rec


def _public(rec: dict) -> dict:
    """不把服务器上的文件路径暴露给前端。"""
    rec["has_audio"] = bool(rec.get("audio_path")) and Path(rec["audio_path"]).exists()
    rec.pop("audio_path", None)
    return rec


def _check_num_speakers(n: Optional[int]) -> Optional[int]:
    if n is not None and not 1 <= n <= 10:
        raise HTTPException(400, "说话人数需要在 1~10 之间")
    return n


def _check_analyzer_ids(ids: Optional[list[str]]) -> Optional[str]:
    """校验要跑的分析器，返回存进数据库的 JSON；None 表示用默认启用的那些。"""
    if ids is None:
        return None
    known = {a.id for a in analyzers.load_analyzers()}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise HTTPException(400, f"没有这些分析器：{', '.join(unknown)}")
    return json.dumps(list(dict.fromkeys(ids)))


def _get_analyzer(analyzer_id: str) -> Analyzer:
    for a in analyzers.effective_analyzers():
        if a.id == analyzer_id:
            return a
    raise HTTPException(404, "分析器不存在")


def _llm_errors(fn, *args):
    """大模型相关接口统一的错误处理：参数问题 400，没配置 400，接口失败 502。"""
    try:
        return fn(*args)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except llm.LLMNotConfigured as e:
        raise HTTPException(400, str(e)) from e
    except llm.LLMError as e:
        raise HTTPException(502, str(e)) from e


@app.get("/api/health")
def health():
    return {
        "version": __version__,
        "asr_engine": settings.asr_engine,
        "llm_model": settings.llm_model,
        "llm_configured": settings.llm_configured,
        "ffmpeg": audio.ffmpeg_available(),
    }


# ---------- 分析器 ----------

@app.get("/api/analyzers")
def list_analyzers():
    return [a.public() for a in analyzers.effective_analyzers()]


class RuleDraft(BaseModel):
    rule: str


@app.post("/api/analyzers/draft")
def draft_analyzer(body: RuleDraft):
    """把一句话的规则描述交给大模型，生成分析器草稿（不保存）。"""
    return _llm_errors(rules.compile_rule, body.rule)


class AnalyzerBody(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    kind: str
    description: str = Field("", max_length=200)
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    rule: str = Field("", max_length=rules.MAX_RULE_CHARS)

    def to_analyzer(self, analyzer_id: str, version: int = 1) -> Analyzer:
        if self.kind not in KINDS:
            raise HTTPException(400, f"kind 只能是 {', '.join(KINDS)} 之一")
        return Analyzer(id=analyzer_id, name=self.name.strip(), kind=self.kind, prompt=self.prompt.strip(),
                        description=self.description.strip(), version=version, rule=self.rule.strip())


class PreviewBody(AnalyzerBody):
    recording_id: str


@app.post("/api/analyzers/preview")
def preview_analyzer(body: PreviewBody):
    """在一段已有录音上试跑还没保存的分析器，结果不入库。"""
    _get_recording(body.recording_id)
    return {"items": _llm_errors(pipeline.preview, body.recording_id, body.to_analyzer("preview"))}


@app.post("/api/analyzers")
def create_analyzer(body: AnalyzerBody):
    a = body.to_analyzer(f"custom_{uuid.uuid4().hex[:8]}")
    analyzers.save_custom(a)
    return _get_analyzer(a.id).detail()


@app.get("/api/analyzers/{analyzer_id}")
def get_analyzer(analyzer_id: str):
    return _get_analyzer(analyzer_id).detail()


def _get_custom(analyzer_id: str) -> Analyzer:
    a = _get_analyzer(analyzer_id)
    if not a.custom:
        raise HTTPException(403, "内置分析器不能在界面上修改或删除，可以停用")
    return a


@app.put("/api/analyzers/{analyzer_id}")
def update_analyzer(analyzer_id: str, body: AnalyzerBody):
    old = _get_custom(analyzer_id)
    analyzers.save_custom(body.to_analyzer(analyzer_id, old.version + 1))
    return _get_analyzer(analyzer_id).detail()


@app.delete("/api/analyzers/{analyzer_id}")
def delete_analyzer(analyzer_id: str):
    analyzers.delete_custom(_get_custom(analyzer_id))
    return {"ok": True}


class AnalyzerPatch(BaseModel):
    enabled: bool


@app.patch("/api/analyzers/{analyzer_id}")
def toggle_analyzer(analyzer_id: str, body: AnalyzerPatch):
    """设置默认是否启用。新录音没有单独勾选时，只跑启用的分析器。"""
    _get_analyzer(analyzer_id)
    analyzers.set_enabled(analyzer_id, body.enabled)
    return _get_analyzer(analyzer_id).public()


# ---------- 录音 ----------

@app.post("/api/recordings")
async def upload_recording(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    num_speakers: Optional[int] = Form(None),
    analyzer_ids: Optional[str] = Form(None, alias="analyzers"),  # JSON 数组，例如 ["diary", "todo"]
):
    num_speakers = _check_num_speakers(num_speakers)
    try:
        selected = _check_analyzer_ids(json.loads(analyzer_ids) if analyzer_ids else None)
    except (json.JSONDecodeError, TypeError) as e:
        raise HTTPException(400, "analyzers 需要是分析器 id 组成的 JSON 数组") from e
    rec_id = uuid.uuid4().hex[:12]
    suffix = Path(file.filename or "").suffix.lower() or ".webm"
    path = settings.audio_dir / f"{rec_id}{suffix}"
    with path.open("wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)

    with connect() as conn:
        conn.execute(
            """INSERT INTO recordings (id, title, filename, audio_path, duration_ms, num_speakers, analyzers)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rec_id, title, file.filename, str(path), audio.probe_duration_ms(path), num_speakers, selected),
        )
    background.add_task(pipeline.process, rec_id, path)
    return _public(_get_recording(rec_id))


@app.get("/api/recordings")
def list_recordings():
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.*,
                 (SELECT COUNT(*) FROM insights i WHERE i.recording_id = r.id AND i.kind = 'insight' AND i.level = 'warning') AS warnings,
                 (SELECT COUNT(*) FROM todos t WHERE t.recording_id = r.id AND t.done = 0) AS open_todos
               FROM recordings r ORDER BY r.created_at DESC"""
        ).fetchall()
    return [_public(r) for r in rows_to_dicts(rows)]


@app.get("/api/recordings/{rec_id}")
def get_recording(rec_id: str):
    rec = _get_recording(rec_id)
    with connect() as conn:
        rec["segments"] = rows_to_dicts(conn.execute(
            "SELECT idx, start_ms, end_ms, speaker, text, emotion FROM segments WHERE recording_id = ? ORDER BY idx",
            (rec_id,)).fetchall())
        rec["speakers"] = rows_to_dicts(conn.execute(
            """SELECT sp.speaker, p.id AS person_id, p.name FROM speakers sp
               LEFT JOIN people p ON p.id = sp.person_id WHERE sp.recording_id = ? ORDER BY sp.speaker""",
            (rec_id,)).fetchall())
        rec["insights"] = rows_to_dicts(conn.execute(
            "SELECT * FROM insights WHERE recording_id = ? ORDER BY kind DESC, id", (rec_id,)).fetchall())
        rec["todos"] = rows_to_dicts(conn.execute(
            "SELECT * FROM todos WHERE recording_id = ? ORDER BY done, id", (rec_id,)).fetchall())
    return _public(rec)


@app.get("/api/recordings/{rec_id}/audio")
def get_audio(rec_id: str):
    rec = _get_recording(rec_id)
    if not rec.get("audio_path") or not Path(rec["audio_path"]).exists():
        raise HTTPException(404, "原始音频已删除")
    return FileResponse(rec["audio_path"])


@app.delete("/api/recordings/{rec_id}")
def delete_recording(rec_id: str):
    rec = _get_recording(rec_id)
    if rec.get("audio_path"):
        Path(rec["audio_path"]).unlink(missing_ok=True)
    with connect() as conn:
        conn.execute("DELETE FROM recordings WHERE id = ?", (rec_id,))
    return {"ok": True}


class AnalyzeOptions(BaseModel):
    analyzers: Optional[list[str]] = None  # None = 沿用这段录音上次的选择


@app.post("/api/recordings/{rec_id}/analyze")
def reanalyze(rec_id: str, background: BackgroundTasks, body: Optional[AnalyzeOptions] = None):
    """重新分析。只替换这次选中的分析器的结果，没选上的分析器结果保留。"""
    rec = _get_recording(rec_id)
    if rec["status"] not in ("done", "error"):
        raise HTTPException(409, "这段录音正在处理中")
    if body is not None and body.analyzers is not None:
        with connect() as conn:
            conn.execute("UPDATE recordings SET analyzers = ? WHERE id = ?", (_check_analyzer_ids(body.analyzers), rec_id))
    background.add_task(pipeline.analyze, rec_id)
    return {"ok": True}


class TranscribeOptions(BaseModel):
    num_speakers: Optional[int] = None  # None = 自动判断


@app.post("/api/recordings/{rec_id}/transcribe")
def retranscribe(rec_id: str, body: TranscribeOptions, background: BackgroundTasks):
    """用新的说话人数重新转写并分析。会清空原有的说话人标注和分析结果（已完成的待办保留）。"""
    rec = _get_recording(rec_id)
    if not rec.get("audio_path") or not Path(rec["audio_path"]).exists():
        raise HTTPException(409, "原始音频已删除，无法重新转写")
    if rec["status"] not in ("done", "error"):
        raise HTTPException(409, "这段录音正在处理中")
    with connect() as conn:
        conn.execute("UPDATE recordings SET num_speakers = ?, status = 'queued', error = NULL WHERE id = ?",
                     (_check_num_speakers(body.num_speakers), rec_id))
    background.add_task(pipeline.process, rec_id, Path(rec["audio_path"]))
    return {"ok": True}


class SpeakerName(BaseModel):
    name: str


@app.put("/api/recordings/{rec_id}/speakers/{speaker}")
def name_speaker(rec_id: str, speaker: str, body: SpeakerName):
    """给说话人标角色。人物跨录音共享，后续会基于声纹自动识别（见路线图）。"""
    _get_recording(rec_id)
    name = body.name.strip()
    with connect() as conn:
        person_id = None
        if name:
            conn.execute("INSERT OR IGNORE INTO people (name) VALUES (?)", (name,))
            person_id = conn.execute("SELECT id FROM people WHERE name = ?", (name,)).fetchone()[0]
        cur = conn.execute(
            "UPDATE speakers SET person_id = ? WHERE recording_id = ? AND speaker = ?", (person_id, rec_id, speaker))
        if cur.rowcount == 0:
            raise HTTPException(404, "说话人不存在")
    return {"speaker": speaker, "person_id": person_id, "name": name or None}


@app.get("/api/people")
def list_people():
    with connect() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM people ORDER BY name").fetchall())


# ---------- 待办 & 洞察 ----------

@app.get("/api/todos")
def list_todos(done: Optional[bool] = None):
    sql = """SELECT t.*, r.title AS recording_title FROM todos t
             LEFT JOIN recordings r ON r.id = t.recording_id"""
    args: tuple = ()
    if done is not None:
        sql += " WHERE t.done = ?"
        args = (int(done),)
    with connect() as conn:
        return rows_to_dicts(conn.execute(sql + " ORDER BY t.done, t.created_at DESC", args).fetchall())


class TodoPatch(BaseModel):
    done: Optional[bool] = None
    title: Optional[str] = None


@app.patch("/api/todos/{todo_id}")
def update_todo(todo_id: int, body: TodoPatch):
    with connect() as conn:
        if body.done is not None:
            conn.execute("UPDATE todos SET done = ? WHERE id = ?", (int(body.done), todo_id))
        if body.title:
            conn.execute("UPDATE todos SET title = ? WHERE id = ?", (body.title, todo_id))
        row = conn.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "待办不存在")
    return row_to_dict(row)


@app.delete("/api/todos/{todo_id}")
def delete_todo(todo_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    return {"ok": True}


class Feedback(BaseModel):
    value: Optional[str] = None  # up | down | None


@app.post("/api/insights/{insight_id}/feedback")
def insight_feedback(insight_id: int, body: Feedback):
    if body.value not in (None, "up", "down"):
        raise HTTPException(400, "value 只能是 up / down / null")
    with connect() as conn:
        conn.execute("UPDATE insights SET feedback = ? WHERE id = ?", (body.value, insight_id))
    return {"ok": True}


if settings.frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
