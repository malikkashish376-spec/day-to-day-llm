"""SQLite persistence layer.

Deliberate choice: a single embedded file database instead of Postgres. The
project is a single-user personal assistant, so the whole data model fits in
one file, needs zero operational overhead during a viva, and still gives us
ACID guarantees plus FTS5 for retrieval. The repository pattern below keeps
SQL out of the tool layer, so swapping in Postgres later touches one module.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .config import settings

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    due_at       TEXT,
    priority     TEXT    NOT NULL DEFAULT 'normal'
                 CHECK (priority IN ('low', 'normal', 'high')),
    status       TEXT    NOT NULL DEFAULT 'open'
                 CHECK (status IN ('open', 'done', 'dropped')),
    tags         TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks(status, due_at);

-- Money is stored in minor units (paise/cents) as an integer. Floating point
-- currency columns silently lose paise and make month totals disagree with
-- the sum of the rows, which is exactly the kind of bug a demo cannot hide.
CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency     TEXT    NOT NULL DEFAULT 'INR',
    category     TEXT    NOT NULL DEFAULT 'other',
    note         TEXT    NOT NULL DEFAULT '',
    spent_on     TEXT    NOT NULL,
    created_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_expenses_month ON expenses(spent_on);

CREATE TABLE IF NOT EXISTS journal (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    entry      TEXT    NOT NULL,
    mood       INTEGER NOT NULL DEFAULT 3 CHECK (mood BETWEEN 1 AND 5),
    energy     INTEGER NOT NULL DEFAULT 3 CHECK (energy BETWEEN 1 AND 5),
    tags       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_journal_created ON journal(created_at);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    tags       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS note_chunks (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    content TEXT    NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(
    content,
    chunk_id UNINDEXED,
    note_id  UNINDEXED,
    tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS session_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    summary    TEXT    NOT NULL,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_audit (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    tool        TEXT    NOT NULL,
    arguments   TEXT    NOT NULL,
    result      TEXT    NOT NULL,
    ok          INTEGER NOT NULL,
    latency_ms  INTEGER NOT NULL,
    created_at  TEXT    NOT NULL
);
"""


def utcnow() -> str:
    """Timestamps are stored in UTC ISO-8601; formatting happens at the edge."""
    return datetime.utcnow().replace(microsecond=0).isoformat()


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path or settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_db(db_path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}
