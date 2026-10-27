"""处理流水线：音频 → 转写 + 说话人 → 各分析器 → 入库。"""
from __future__ import annotations

import json
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from . import audio, llm
from .analyzers import COMMON_SPEC, OUTPUT_SPECS, Analyzer, effective_analyzers
from .asr import get_engine
from .config import settings
from .db import connect

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是「弦外」，一个帮用户整理日常对话的助手。
规则：
1. 只依据转写内容下结论，不臆测转写里没有的事实。
2. 每条结论都必须在 evidence 里给出支撑它的片段编号（转写中的 #n）。
3. 拿不准就降低 confidence，宁可不说也不要编造。
4. 描述行为和话术，不要给人下定性判断（例如不说「他是坏人」）。
5. 只输出 JSON，不要输出其他文字。"""


def _set_status(rec_id: str, status: str, error: str | None = None) -> None:
    with connect() as conn:
        conn.execute("UPDATE recordings SET status = ?, error = ? WHERE id = ?", (status, error, rec_id))


def _fmt_ts(ms: int) -> str:
    s = ms // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def build_transcript(rec_id: str) -> tuple[str, set[int]]:
    """转写文本里用人物名代替 S1/S2，用户标注过角色后重新分析会更准。"""
    with connect() as conn:
        rows = conn.execute(
            """SELECT s.idx, s.start_ms, s.speaker, s.text, s.emotion, p.name AS person
               FROM segments s
               LEFT JOIN speakers sp ON sp.recording_id = s.recording_id AND sp.speaker = s.speaker
               LEFT JOIN people p ON p.id = sp.person_id
               WHERE s.recording_id = ? ORDER BY s.idx""",
            (rec_id,),
        ).fetchall()
    return format_transcript([dict(r) for r in rows]), {r["idx"] for r in rows}


def format_transcript(rows: list[dict]) -> str:
    """rows 需要 idx / start_ms / speaker / text，可选 person / emotion。"""
    lines = []
    for r in rows:
        who = r.get("person") or r["speaker"]
        emo = f"（情绪:{r['emotion']}）" if r.get("emotion") else ""
        lines.append(f"#{r['idx']} [{_fmt_ts(r['start_ms'])}] {who}{emo}：{r['text']}")
    return "\n".join(lines)


def _clean_evidence(value: Any, valid: set[int]) -> list[int]:
    if not isinstance(value, list):
        value = [value]
    out = []
    for v in value:
        try:
            n = int(str(v).lstrip("#"))
        except ValueError:
            continue
        if n in valid and n not in out:
            out.append(n)
    return out


def _confidence(value: Any) -> float | None:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def call_analyzer(analyzer: Analyzer, transcript: str) -> dict[str, Any]:
    user = (
        f"{analyzer.prompt.strip()}\n\n"
        f"请按以下 JSON 结构输出：\n{OUTPUT_SPECS[analyzer.kind]}\n{COMMON_SPEC}\n\n"
        f"对话转写：\n{transcript}"
    )
    return llm.chat_json(SYSTEM_PROMPT, user)


def normalize(kind: str, data: dict[str, Any], valid: set[int]) -> list[dict[str, Any]]:
    """把模型输出整理成要入库的条目：丢掉无效项和不存在的片段编号，修正等级和置信度。"""
    if kind == "summary":
        highlights = [h for h in data.get("highlights") or [] if isinstance(h, dict)]
        evidence = sorted({n for h in highlights for n in _clean_evidence(h.get("evidence", []), valid)})
        detail = data.get("summary", "")
        if highlights:
            detail += "\n" + "\n".join(f"· {h.get('text', '')}" for h in highlights)
        return [{"title": data.get("title", ""), "detail": detail.strip(), "evidence": evidence}]

    if kind == "todo":
        return [
            {"title": t["title"], "detail": t.get("detail"), "owner": t.get("owner"), "due": t.get("due"),
             "confidence": _confidence(t.get("confidence")), "evidence": _clean_evidence(t.get("evidence", []), valid)}
            for t in data.get("todos") or [] if isinstance(t, dict) and t.get("title")
        ]

    return [
        {"level": i.get("level") if i.get("level") in ("info", "notice", "warning") else "info",
         "title": i["title"], "detail": i.get("detail"),
         "confidence": _confidence(i.get("confidence")), "evidence": _clean_evidence(i.get("evidence", []), valid)}
        for i in data.get("insights") or [] if isinstance(i, dict) and i.get("title")
    ]


def run_analyzer(rec_id: str, analyzer: Analyzer, transcript: str, valid: set[int]) -> None:
    items = normalize(analyzer.kind, call_analyzer(analyzer, transcript), valid)

    with connect() as conn:
        if analyzer.kind == "summary":
            [s] = items
            conn.execute(
                "INSERT INTO insights (recording_id, analyzer_id, kind, title, detail, evidence) VALUES (?, ?, 'summary', ?, ?, ?)",
                (rec_id, analyzer.id, s["title"], s["detail"], json.dumps(s["evidence"])),
            )
            if s["title"]:
                conn.execute("UPDATE recordings SET title = ? WHERE id = ? AND (title IS NULL OR title = '')", (s["title"], rec_id))

        elif analyzer.kind == "todo":
            # 重新分析时，已完成的待办被保留了，不要再生成一遍
            done_titles = {r[0] for r in conn.execute(
                "SELECT title FROM todos WHERE recording_id = ? AND done = 1", (rec_id,))}
            for t in items:
                if t["title"] in done_titles:
                    continue
                conn.execute(
                    """INSERT INTO todos (recording_id, analyzer_id, title, detail, owner, due, confidence, evidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (rec_id, analyzer.id, t["title"], t["detail"], t["owner"], t["due"], t["confidence"], json.dumps(t["evidence"])),
                )

        else:  # insight
            for i in items:
                conn.execute(
                    """INSERT INTO insights (recording_id, analyzer_id, kind, level, title, detail, confidence, evidence)
                       VALUES (?, ?, 'insight', ?, ?, ?, ?, ?)""",
                    (rec_id, analyzer.id, i["level"], i["title"], i["detail"], i["confidence"], json.dumps(i["evidence"])),
                )


def selected_analyzers(rec_id: str) -> list[Analyzer]:
    """这段录音要跑的分析器：用户勾选过就按勾选的来，否则用默认启用的。"""
    with connect() as conn:
        row = conn.execute("SELECT analyzers FROM recordings WHERE id = ?", (rec_id,)).fetchone()
    analyzers = effective_analyzers()
    if row is None or row[0] is None:
        return [a for a in analyzers if a.enabled]
    by_id = {a.id: a for a in analyzers}
    return [by_id[i] for i in json.loads(row[0]) if i in by_id]  # 已被删除的分析器直接跳过


def preview(rec_id: str, analyzer: Analyzer) -> list[dict[str, Any]]:
    """试跑：在一段录音上运行分析器，结果直接返回，不入库。"""
    transcript, valid = build_transcript(rec_id)
    if not transcript:
        raise ValueError("这段录音没有转写内容")
    return normalize(analyzer.kind, call_analyzer(analyzer, transcript), valid)


def analyze(rec_id: str) -> None:
    """（重新）运行选中的分析器。只替换这些分析器的旧结果；没选上的分析器结果和已完成的待办都保留。"""
    _set_status(rec_id, "analyzing")
    analyzers = selected_analyzers(rec_id)
    ids = [a.id for a in analyzers]
    if ids:
        marks = ",".join("?" * len(ids))
        with connect() as conn:
            conn.execute(f"DELETE FROM insights WHERE recording_id = ? AND analyzer_id IN ({marks})", (rec_id, *ids))
            conn.execute(f"DELETE FROM todos WHERE recording_id = ? AND done = 0 AND analyzer_id IN ({marks})", (rec_id, *ids))

    transcript, valid = build_transcript(rec_id)
    if not transcript:
        _set_status(rec_id, "done", "没有识别到语音内容")
        return

    errors = []
    for analyzer in analyzers:
        t0 = time.time()
        try:
            run_analyzer(rec_id, analyzer, transcript, valid)
            log.info("分析器 %s 完成，用时 %.0fs", analyzer.id, time.time() - t0)
        except llm.LLMNotConfigured as e:
            errors = [str(e)]
            break
        except Exception as e:
            log.exception("分析器 %s 失败", analyzer.id)
            errors.append(f"{analyzer.name}: {e}")
    _set_status(rec_id, "done", "；".join(errors) or None)


def transcribe(rec_id: str, audio_path: Path) -> None:
    _set_status(rec_id, "transcribing")
    engine = get_engine(settings.asr_engine)
    with connect() as conn:
        num_speakers = conn.execute("SELECT num_speakers FROM recordings WHERE id = ?", (rec_id,)).fetchone()[0]
    with tempfile.TemporaryDirectory() as tmp:
        src = audio.to_wav16k(audio_path, Path(tmp) / "in.wav") if engine.needs_wav else audio_path
        segments = engine.transcribe(src, num_speakers)

    with connect() as conn:
        conn.execute("DELETE FROM segments WHERE recording_id = ?", (rec_id,))
        # 重新转写后说话人编号会变，旧的标注作废
        conn.execute("DELETE FROM speakers WHERE recording_id = ?", (rec_id,))
        conn.executemany(
            "INSERT INTO segments (recording_id, idx, start_ms, end_ms, speaker, text, emotion) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(rec_id, i + 1, s.start_ms, s.end_ms, s.speaker, s.text, s.emotion) for i, s in enumerate(segments)],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO speakers (recording_id, speaker) VALUES (?, ?)",
            [(rec_id, spk) for spk in sorted({s.speaker for s in segments})],
        )
        if segments and not conn.execute("SELECT duration_ms FROM recordings WHERE id = ?", (rec_id,)).fetchone()[0]:
            conn.execute("UPDATE recordings SET duration_ms = ? WHERE id = ?", (segments[-1].end_ms, rec_id))


def process(rec_id: str, audio_path: Path) -> None:
    try:
        transcribe(rec_id, audio_path)
        analyze(rec_id)
    except Exception as e:
        log.exception("处理录音 %s 失败", rec_id)
        _set_status(rec_id, "error", str(e))
        return
    if not settings.keep_audio:
        audio_path.unlink(missing_ok=True)
        with connect() as conn:
            conn.execute("UPDATE recordings SET audio_path = NULL WHERE id = ?", (rec_id,))
