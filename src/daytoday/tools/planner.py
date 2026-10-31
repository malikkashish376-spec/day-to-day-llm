"""Day planning and weekly review.

The plan is computed deterministically from stored state (a constraint pass
over deadlines, priority and available hours) and the LLM only narrates it.
Asking a model to invent a schedule produced plans that referenced tasks the
user never created; doing the arithmetic in Python and the language in the
model removed that class of error entirely.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, time, timedelta
from typing import Any

from ..config import settings
from ..formatting import fmt_money, truncate
from ..timeparse import humanise, now_local, parse_when
from .registry import Tool

WORK_START = time(9, 30)
BLOCK_MINUTES = 50
BREAK_MINUTES = 10
MAX_BLOCKS = 6


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _candidates(conn: sqlite3.Connection, target: datetime) -> list[dict[str, Any]]:
    rows = list(conn.execute(
        "SELECT * FROM tasks WHERE status = 'open' ORDER BY (due_at IS NULL), due_at ASC"))
    weight = {"high": 0, "normal": 1, "low": 2}
    scored = []
    for row in rows:
        due = _parse(row["due_at"])
        if due and due < now_local():
            bucket = 0                      # overdue first
        elif due and due.date() == target.date():
            bucket = 1                      # due on the target day
        elif due and (due.date() - target.date()).days <= 3:
            bucket = 2                      # due this week
        elif due is None and row["priority"] == "high":
            bucket = 3                      # undated but flagged
        elif due is None:
            bucket = 4
        else:
            bucket = 5
        scored.append((bucket, weight.get(row["priority"], 1), row["id"], {
            "id": row["id"],
            "title": row["title"],
            "priority": row["priority"],
            "due_human": humanise(due) if due else None,
            "overdue": bool(due and due < now_local()),
        }))
    scored.sort(key=lambda item: item[:3])
    return [item[3] for item in scored]


def _label(target: datetime, today: datetime) -> str:
    """'today' / 'tomorrow' / 'Mon 3 Nov' -- never a bare 09:00 default time."""
    delta = (target.date() - today.date()).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    return target.strftime("%a %-d %b")


def plan_day(conn: sqlite3.Connection, *, session_id: str,
             when: str | None = None) -> dict[str, Any]:
    target = parse_when(when) or now_local()
    today = now_local()
    tasks = _candidates(conn, target)

    # Do not schedule into the past: on a same-day request the first block
    # starts at the next quarter hour after "now".
    start = datetime.combine(target.date(), WORK_START)
    if target.date() == today.date():
        ahead = (today + timedelta(minutes=15)).replace(second=0, microsecond=0)
        start = max(start, ahead.replace(minute=(ahead.minute // 15) * 15))

    blocks: list[dict[str, Any]] = []
    cursor = start
    for task in tasks[:MAX_BLOCKS]:
        end = cursor + timedelta(minutes=BLOCK_MINUTES)
        blocks.append({
            "start": cursor.strftime("%H:%M"),
            "end": end.strftime("%H:%M"),
            "task_id": task["id"],
            "title": task["title"],
            "priority": task["priority"],
            "flag": "overdue" if task["overdue"] else task["priority"],
        })
        cursor = end + timedelta(minutes=BREAK_MINUTES)

    spend = conn.execute(
        "SELECT COALESCE(SUM(amount_minor),0) AS total FROM expenses WHERE spent_on = ?",
        (target.date().isoformat(),)).fetchone()["total"]
    mood_row = conn.execute(
        "SELECT AVG(mood) AS mood, AVG(energy) AS energy FROM journal"
        " WHERE substr(created_at,1,10) >= ?",
        ((target.date() - timedelta(days=7)).isoformat(),)).fetchone()

    overdue = [task for task in tasks if task["overdue"]]
    deep_work = len(blocks)
    if overdue:
        coach = (f"{len(overdue)} task(s) are already past due - clear "
                 f"'{truncate(overdue[0]['title'], 40)}' first, then re-plan.")
    elif mood_row["energy"] is not None and mood_row["energy"] < 2.5:
        coach = ("Energy has been low this week. Plan the hardest block first and keep "
                 "the afternoon light.")
    elif deep_work == 0:
        coach = "Nothing is pending for this day. Good slot for revision or a buffer."
    else:
        coach = (f"{deep_work} focus block(s) scheduled. Stop after block "
                 f"{min(deep_work, 3)} for a real break.")

    return {
        "ok": True,
        "date": target.date().isoformat(),
        "date_human": _label(target, today),
        "blocks": blocks,
        "unscheduled": [task["title"] for task in tasks[MAX_BLOCKS:]],
        "pending_count": len(tasks),
        "overdue_count": len(overdue),
        "spend_today": fmt_money(spend, settings.currency),
        "mood_7d": round(mood_row["mood"], 2) if mood_row["mood"] else None,
        "coach_note": coach,
    }


def weekly_review(conn: sqlite3.Connection, *, session_id: str) -> dict[str, Any]:
    today = now_local().date()
    week_start = (today - timedelta(days=6)).isoformat()
    prev_start = (today - timedelta(days=13)).isoformat()
    prev_end = (today - timedelta(days=7)).isoformat()

    done = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE status='done' AND substr(completed_at,1,10) >= ?",
        (week_start,)).fetchone()["n"]
    open_count = conn.execute("SELECT COUNT(*) AS n FROM tasks WHERE status='open'").fetchone()["n"]
    overdue = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE status='open' AND due_at IS NOT NULL"
        " AND due_at < ?", (now_local().isoformat(),)).fetchone()["n"]
    this_week = conn.execute(
        "SELECT COALESCE(SUM(amount_minor),0) AS t FROM expenses WHERE spent_on >= ?",
        (week_start,)).fetchone()["t"]
    last_week = conn.execute(
        "SELECT COALESCE(SUM(amount_minor),0) AS t FROM expenses WHERE spent_on BETWEEN ? AND ?",
        (prev_start, prev_end)).fetchone()["t"]
    top = conn.execute(
        "SELECT category, SUM(amount_minor) AS t FROM expenses WHERE spent_on >= ?"
        " GROUP BY category ORDER BY t DESC LIMIT 1", (week_start,)).fetchone()
    mood = conn.execute(
        "SELECT AVG(mood) AS m FROM journal WHERE substr(created_at,1,10) >= ?",
        (week_start,)).fetchone()["m"]

    delta = None
    if last_week:
        delta = round(100 * (this_week - last_week) / last_week, 1)

    return {
        "ok": True, "from": week_start, "to": today.isoformat(),
        "tasks_completed": done, "tasks_open": open_count, "tasks_overdue": overdue,
        "spend_this_week": fmt_money(this_week, settings.currency),
        "spend_last_week": fmt_money(last_week, settings.currency),
        "spend_change_pct": delta,
        "top_category": top["category"] if top else None,
        "average_mood": round(mood, 2) if mood else None,
    }


TOOLS = [
    Tool(
        name="plan_day",
        description="Build a time-blocked plan for a day from pending tasks, deadlines, "
                    "recent spending and energy levels.",
        parameters={
            "type": "object",
            "properties": {
                "when": {"type": "string",
                         "description": "'today', 'tomorrow' or a date phrase. Defaults to today."},
            },
        },
        handler=plan_day,
    ),
    Tool(
        name="weekly_review",
        description="Summarise the last seven days: tasks completed, overdue items, spending "
                    "versus the previous week, and average mood.",
        parameters={"type": "object", "properties": {}},
        handler=weekly_review,
    ),
]
