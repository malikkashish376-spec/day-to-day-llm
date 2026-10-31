"""Note capture and retrieval-backed question answering."""
from __future__ import annotations

import sqlite3
from typing import Any

from .. import rag
from ..config import settings
from ..db import utcnow
from .registry import Tool, ToolError


def add_note(conn: sqlite3.Connection, *, session_id: str, body: str,
             title: str | None = None, tags: str = "") -> dict[str, Any]:
    body = (body or "").strip()
    if len(body) < 5:
        raise ToolError("note body is too short to index")
    title = (title or "").strip() or body.split(".")[0][:60].strip() or "Untitled note"
    cursor = conn.execute(
        "INSERT INTO notes (title, body, tags, created_at) VALUES (?,?,?,?)",
        (title, body, tags, utcnow()))
    chunks = rag.index_note(conn, cursor.lastrowid, body)
    return {"ok": True, "note_id": cursor.lastrowid, "title": title, "chunks_indexed": chunks,
            "message": f"Saved note '{title}' ({chunks} chunk(s) indexed)."}


def search_notes(conn: sqlite3.Connection, *, session_id: str, query: str,
                 k: int | None = None) -> dict[str, Any]:
    k = int(k or settings.retrieval_k)
    hits = rag.search_notes(conn, query, k=k)
    return {"ok": True, "query": query, "hits": hits, "count": len(hits),
            "message": (f"Found {len(hits)} matching note chunk(s)." if hits
                        else "Nothing in the notes matches that query.")}


TOOLS = [
    Tool(
        name="add_note",
        description="Store a note, idea, meeting summary or study material for later recall.",
        parameters={
            "type": "object",
            "properties": {
                "body": {"type": "string", "description": "Full note text."},
                "title": {"type": "string"},
                "tags": {"type": "string"},
            },
            "required": ["body"],
        },
        handler=add_note,
    ),
    Tool(
        name="search_notes",
        description="Search the user's own notes. Use for any question that may be answered "
                    "from something the user wrote down earlier.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "description": "How many chunks to return."},
            },
            "required": ["query"],
        },
        handler=search_notes,
    ),
]
