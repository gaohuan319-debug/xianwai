"""SQLite 存储。零运维，数据就在用户自己的磁盘上。"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS recordings (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    filename    TEXT,
    audio_path  TEXT,
    duration_ms INTEGER,
    num_speakers INTEGER,  -- 用户指定的说话人数，NULL 表示自动
    status      TEXT NOT NULL DEFAULT 'queued',  -- queued | transcribing | analyzing | done | error
    error       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS segments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    idx          INTEGER NOT NULL,
    start_ms     INTEGER NOT NULL,
    end_ms       INTEGER NOT NULL,
    speaker      TEXT NOT NULL,
    text         TEXT NOT NULL,
    emotion      TEXT
);

CREATE TABLE IF NOT EXISTS people (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    note TEXT
);

-- 每段录音里的说话人（S1/S2...）对应到哪个人物
CREATE TABLE IF NOT EXISTS speakers (
    recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    speaker      TEXT NOT NULL,
    person_id    INTEGER REFERENCES people(id) ON DELETE SET NULL,
    PRIMARY KEY (recording_id, speaker)
);

-- kind = summary（日记摘要）| insight（沟通洞察）
CREATE TABLE IF NOT EXISTS insights (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    analyzer_id  TEXT NOT NULL,
    kind         TEXT NOT NULL,
    level        TEXT,
    title        TEXT,
    detail       TEXT,
    confidence   REAL,
    evidence     TEXT NOT NULL DEFAULT '[]',
    feedback     TEXT,  -- up | down，用户纠错
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS todos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id TEXT REFERENCES recordings(id) ON DELETE SET NULL,
    analyzer_id  TEXT,
    title        TEXT NOT NULL,
    detail       TEXT,
    owner        TEXT,
    due          TEXT,
    confidence   REAL,
    evidence     TEXT NOT NULL DEFAULT '[]',
    done         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

_JSON_COLUMNS = {"evidence"}


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        # 旧版数据库补字段
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(recordings)")}
        if "num_speakers" not in cols:
            conn.execute("ALTER TABLE recordings ADD COLUMN num_speakers INTEGER")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    for col in _JSON_COLUMNS & d.keys():
        d[col] = json.loads(d[col] or "[]")
    return d


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(r) for r in rows]  # type: ignore[misc]
