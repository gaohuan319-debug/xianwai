from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__, audio, pipeline
from .analyzers import load_analyzers
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


@app.get("/api/health")
def health():
    return {
        "version": __version__,
        "asr_engine": settings.asr_engine,
        "llm_model": settings.llm_model,
        "llm_configured": settings.llm_configured,
        "ffmpeg": audio.ffmpeg_available(),
    }


@app.get("/api/analyzers")
def list_analyzers():
    return [a.public() for a in load_analyzers()]


# ---------- 录音 ----------

@app.post("/api/recordings")
async def upload_recording(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    num_speakers: Optional[int] = Form(None),
):
    num_speakers = _check_num_speakers(num_speakers)
    rec_id = uuid.uuid4().hex[:12]
    suffix = Path(file.filename or "").suffix.lower() or ".webm"
    path = settings.audio_dir / f"{rec_id}{suffix}"
    with path.open("wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)

    with connect() as conn:
        conn.execute(
            "INSERT INTO recordings (id, title, filename, audio_path, duration_ms, num_speakers) VALUES (?, ?, ?, ?, ?, ?)",
            (rec_id, title, file.filename, str(path), audio.probe_duration_ms(path), num_speakers),
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


@app.post("/api/recordings/{rec_id}/analyze")
def reanalyze(rec_id: str, background: BackgroundTasks):
    _get_recording(rec_id)
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
