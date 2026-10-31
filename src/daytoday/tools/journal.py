"""Journaling plus a lightweight affect signal.

Mood is stored as a 1-5 integer so it can be plotted and averaged. When the
user writes freely instead of giving a rating, a small lexicon maps the text
onto that scale. It is a heuristic, not a sentiment model, and the API
always tells the user which value was inferred so a wrong guess is correctable.
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta
from typing import Any

from ..db import utcnow
from ..timeparse import now_local
from .registry import Tool, ToolError

POSITIVE = ("good", "great", "happy", "productive", "calm", "grateful", "excited",
            "proud", "relaxed", "energised", "energized", "focused", "better", "won",
            "completed", "finished", "fun", "love", "amazing", "peaceful")
NEGATIVE = ("tired", "exhausted", "stressed", "anxious", "sad", "angry", "burnt",
            "burned", "overwhelmed", "sick", "low", "worst", "hate", "failed",
            "procrastinated", "guilty", "panic", "lonely", "drained", "headache")


def infer_mood(text: str) -> tuple[int, int]:
    """Return (mood, energy) on 1-5 from free text."""
    lowered = text.lower()
    pos = sum(word in lowered for word in POSITIVE)
    neg = sum(word in lowered for word in NEGATIVE)
    if pos > neg:
        mood = 4 if pos > 2 else 4
        if pos - neg >= 2:
            mood = 5
    elif neg > pos:
        mood = 2 if neg == 1 else 1
    else:
        mood = 3
    energy = 3
    if any(word in lowered for word in ("exhausted", "tired", "drained", "burnt", "burned")):
        energy = 2
    elif any(word in lowered for word in ("energised", "energized", "fresh", "motivated")):
        energy = 4
    return mood, energy


def log_journal(conn: sqlite3.Connection, *, session_id: str, entry: str,
                mood: int | None = None, energy: int | None = None,
                tags: str = "") -> dict[str, Any]:
    entry = (entry or "").strip()
    if len(entry) < 3:
        raise ToolError("journal entry is too short to store")
    inferred = False
    if mood is None or energy is None:
        guess_mood, guess_energy = infer_mood(entry)
        mood = mood if mood is not None else guess_mood
        energy = energy if energy is not None else guess_energy
        inferred = True
    mood = max(1, min(5, int(mood)))
    energy = max(1, min(5, int(energy)))
    cursor = conn.execute(
        "INSERT INTO journal (entry, mood, energy, tags, created_at) VALUES (?,?,?,?,?)",
        (entry, mood, energy, tags, utcnow()))
    return {"ok": True, "id": cursor.lastrowid, "mood": mood, "energy": energy,
            "mood_inferred": inferred,
            "message": f"Journal saved (mood {mood}/5, energy {energy}/5)."}


def mood_trend(conn: sqlite3.Connection, *, session_id: str,
               days: int = 14) -> dict[str, Any]:
    since = (now_local() - timedelta(days=int(days))).date().isoformat()
    rows = list(conn.execute(
        "SELECT substr(created_at, 1, 10) AS day, AVG(mood) AS mood, AVG(energy) AS energy,"
        " COUNT(*) AS n FROM journal WHERE substr(created_at, 1, 10) >= ?"
        " GROUP BY day ORDER BY day", (since,)))
    if not rows:
        return {"ok": True, "entries": 0, "average_mood": None, "average_energy": None,
                "series": [], "message": "No journal entries in this window yet."}
    series = [{"day": row["day"], "mood": round(row["mood"], 2),
               "energy": round(row["energy"], 2), "entries": row["n"]} for row in rows]
    avg_mood = round(sum(row["mood"] for row in series) / len(series), 2)
    avg_energy = round(sum(row["energy"] for row in series) / len(series), 2)
    if len(series) >= 4:
        half = len(series) // 2
        early = sum(row["mood"] for row in series[:half]) / half
        late = sum(row["mood"] for row in series[half:]) / (len(series) - half)
        direction = "improving" if late - early > 0.3 else (
            "declining" if early - late > 0.3 else "steady")
    else:
        direction = "not enough data"
    return {"ok": True, "entries": sum(row["entries"] for row in series),
            "average_mood": avg_mood, "average_energy": avg_energy,
            "trend": direction, "series": series}


TOOLS = [
    Tool(
        name="log_journal",
        description="Save a journal entry about how the day went, with mood and energy.",
        parameters={
            "type": "object",
            "properties": {
                "entry": {"type": "string", "description": "The reflection, in the user's words."},
                "mood": {"type": "integer", "description": "1 (very low) to 5 (very good)."},
                "energy": {"type": "integer", "description": "1 (drained) to 5 (fresh)."},
                "tags": {"type": "string"},
            },
            "required": ["entry"],
        },
        handler=log_journal,
    ),
    Tool(
        name="mood_trend",
        description="Average mood and energy over recent days, with direction of travel.",
        parameters={
            "type": "object",
            "properties": {"days": {"type": "integer"}},
        },
        handler=mood_trend,
    ),
]
