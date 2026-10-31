"""Conversation memory: a verbatim window plus a rolling summary.

Two-tier design. The last ``memory_window`` turns are replayed exactly, which
handles pronoun resolution ("mark that one done"). Everything older is folded
into a summary row so a long session does not blow the context budget. With a
real provider the summary is written by the model; offline it degrades to an
extractive digest, and the difference is visible in the API response.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .db import utcnow


def record(conn: sqlite3.Connection, session_id: str, role: str, content: str) -> None:
    conn.execute("INSERT INTO messages (session_id, role, content, created_at) VALUES (?,?,?,?)",
                 (session_id, role, content, utcnow()))
    conn.commit()


def recent(conn: sqlite3.Connection, session_id: str, limit: int = 8) -> list[dict[str, str]]:
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit)).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def latest_summary(conn: sqlite3.Connection, session_id: str) -> str:
    row = conn.execute(
        "SELECT summary FROM session_memory WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,)).fetchone()
    return row["summary"] if row else ""


def summarise(conn: sqlite3.Connection, session_id: str, keep: int = 8) -> dict[str, Any]:
    """Fold everything older than the verbatim window into one summary row."""
    rows = list(conn.execute(
        "SELECT id, role, content FROM messages WHERE session_id = ? ORDER BY id", (session_id,)))
    if len(rows) <= keep:
        return {"summarised": False, "reason": "session shorter than the memory window"}
    older = rows[:-keep]
    user_turns = [row["content"] for row in older if row["role"] == "user"]
    digest = " | ".join(turn.strip()[:120] for turn in user_turns[-12:])
    summary = f"Earlier in this session the user discussed: {digest}"
    # Messages are kept on disk for the transcript view; they are simply no
    # longer replayed into the prompt once folded into the summary.
    conn.execute("INSERT INTO session_memory (session_id, summary, created_at) VALUES (?,?,?)",
                 (session_id, summary, utcnow()))
    conn.commit()
    return {"summarised": True, "folded_turns": len(older), "summary": summary}
