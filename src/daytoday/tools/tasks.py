"""Task capture, listing and completion."""
from __future__ import annotations

import difflib
import sqlite3
from datetime import timedelta
from typing import Any

from ..db import utcnow
from ..formatting import truncate
from ..timeparse import humanise, now_local, parse_when
from .registry import Tool, ToolError

PRIORITIES = ("low", "normal", "high")


def _row(row: sqlite3.Row) -> dict[str, Any]:
    due = row["due_at"]
    return {
        "id": row["id"],
        "title": row["title"],
        "due_at": due,
        "due_human": humanise(_parse(due)) if due else None,
        "priority": row["priority"],
        "status": row["status"],
        "tags": row["tags"],
    }


def _parse(value: str | None):
    from datetime import datetime
    return datetime.fromisoformat(value) if value else None


def add_task(conn: sqlite3.Connection, *, session_id: str, title: str,
             when: str | None = None, priority: str = "normal",
             tags: str = "") -> dict[str, Any]:
    title = title.strip()
    if not title:
        raise ToolError("task title is empty")
    priority = (priority or "normal").lower()
    if priority not in PRIORITIES:
        priority = "normal"
    due = parse_when(when)
    cursor = conn.execute(
        "INSERT INTO tasks (title, due_at, priority, status, tags, created_at)"
        " VALUES (?,?,?,'open',?,?)",
        (title, due.isoformat() if due else None, priority, tags, utcnow()),
    )
    return {
        "ok": True,
        "task": {"id": cursor.lastrowid, "title": title,
                 "due_human": humanise(due), "priority": priority},
        "message": f"Captured '{title}' ({humanise(due)}, {priority} priority).",
    }


def list_tasks(conn: sqlite3.Connection, *, session_id: str, status: str = "open",
               horizon_days: int = 7) -> dict[str, Any]:
    status = status if status in ("open", "done", "dropped", "all") else "open"
    sql = "SELECT * FROM tasks"
    params: list[Any] = []
    if status != "all":
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY (due_at IS NULL), due_at ASC, id ASC"
    rows = [_row(row) for row in conn.execute(sql, params)]
    cutoff = now_local() + timedelta(days=int(horizon_days))
    upcoming = [row for row in rows
                if row["due_at"] and _parse(row["due_at"]) and _parse(row["due_at"]) <= cutoff]
    overdue = [row for row in rows
               if row["due_at"] and _parse(row["due_at"]) < now_local()]
    return {"ok": True, "count": len(rows), "tasks": rows,
            "overdue_ids": [row["id"] for row in overdue],
            "due_soon_ids": [row["id"] for row in upcoming]}


def complete_task(conn: sqlite3.Connection, *, session_id: str,
                  query: str | None = None, task_id: int | None = None) -> dict[str, Any]:
    open_rows = list(conn.execute("SELECT * FROM tasks WHERE status = 'open' ORDER BY id"))
    if not open_rows:
        raise ToolError("there are no open tasks to complete")
    match: sqlite3.Row | None = None
    if task_id is not None:
        match = next((row for row in open_rows if row["id"] == int(task_id)), None)
    if match is None and query:
        needle = query.lower().strip()
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in open_rows:
            title = row["title"].lower()
            if needle in title:
                score = 1.0 + len(needle) / max(len(title), 1)
            else:
                score = difflib.SequenceMatcher(None, needle, title).ratio()
            scored.append((score, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        if scored and scored[0][0] >= 0.55:
            match = scored[0][1]
    if match is None:
        titles = ", ".join(f"#{row['id']} {truncate(row['title'], 40)}" for row in open_rows[:5])
        raise ToolError(f"no open task matched {query!r}. Open tasks: {titles}")
    conn.execute("UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?",
                 (utcnow(), match["id"]))
    return {"ok": True, "completed": {"id": match["id"], "title": match["title"]},
            "message": f"Marked '{match['title']}' as done."}


TOOLS = [
    Tool(
        name="add_task",
        description="Capture a to-do. Use whenever the user mentions something they must do, "
                    "asks to be reminded, or states an intention with a deadline.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short imperative task title."},
                "when": {"type": "string",
                         "description": "Deadline phrase exactly as spoken, e.g. 'tomorrow 6pm', "
                                        "'by Friday', '25/12'. Omit if none."},
                "priority": {"type": "string", "enum": list(PRIORITIES),
                             "description": "high for hard deadlines or exam/office work."},
                "tags": {"type": "string", "description": "Comma separated labels."},
            },
            "required": ["title"],
        },
        handler=add_task,
    ),
    Tool(
        name="list_tasks",
        description="List the user's tasks with due dates and flag overdue items.",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "done", "dropped", "all"]},
                "horizon_days": {"type": "integer",
                                 "description": "Flag tasks due within this many days."},
            },
        },
        handler=list_tasks,
    ),
    Tool(
        name="complete_task",
        description="Mark a task done. Pass the user's description of the task in 'query'.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words from the task title."},
                "task_id": {"type": "integer"},
            },
        },
        handler=complete_task,
    ),
]
