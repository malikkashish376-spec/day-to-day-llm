"""Deterministic natural-language time parsing.

A general-purpose LLM is good at language and bad at arithmetic on clocks.
Rather than trusting the model to emit an ISO timestamp (it routinely gets
the year and weekday wrong), every tool schema accepts the *raw phrase*
("tomorrow at 6pm") and this module resolves it against the server clock.
That keeps date handling auditable and unit-testable, and it is the reason
the mock provider and a 70B model produce identical stored timestamps.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}

_TIME_RE = re.compile(
    r"\b(?:at|by|around|@)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b",
    re.IGNORECASE,
)
_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DMY_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
_IN_RE = re.compile(r"\bin\s+(\d{1,3})\s*(min|mins|minute|minutes|hour|hours|hr|hrs|day|days)\b",
                    re.IGNORECASE)


def now_local(tz: str = "Asia/Kolkata") -> datetime:
    return datetime.now(ZoneInfo(tz)).replace(tzinfo=None, microsecond=0)


def _parse_clock(text: str) -> time | None:
    """Extract a wall-clock time from a phrase, if one is present."""
    for match in _TIME_RE.finditer(text):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = (match.group(3) or "").replace(".", "").lower()
        if minute > 59 or hour > 23:
            continue
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        elif not meridiem and 0 < hour <= 8:
            # "dinner at 8" / "call at 6" mean the evening, not 08:00. Bare
            # hours 1-8 are read as PM; the user can always say "8am" to
            # override. Documented heuristic, covered by a unit test.
            hour += 12
        # Bare numbers are only a time when a meridiem or colon is present.
        if not meridiem and not match.group(2) and not match.group(0).strip().startswith(("at", "by")):
            continue
        return time(hour=hour, minute=minute)
    return None


def parse_when(phrase: str | None, *, base: datetime | None = None,
               tz: str = "Asia/Kolkata") -> datetime | None:
    """Resolve a free-text time expression to a naive local ``datetime``.

    Returns ``None`` when no temporal information is present, which callers
    treat as "no due date" rather than defaulting to *now*.
    """
    if not phrase:
        return None
    text = phrase.lower().strip()
    base = base or now_local(tz)

    clock = _parse_clock(text)
    day: date | None = None

    if m := _ISO_RE.search(text):
        try:
            day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            day = None
    elif m := _DMY_RE.search(text):
        d, mo = int(m.group(1)), int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else base.year
        if yr < 100:
            yr += 2000
        try:
            day = date(yr, mo, d)
        except ValueError:
            day = None

    if day is None:
        if m := _IN_RE.search(text):
            n, unit = int(m.group(1)), m.group(2).lower()
            delta = timedelta(minutes=n) if unit.startswith("min") else (
                timedelta(hours=n) if unit.startswith(("hour", "hr")) else timedelta(days=n))
            return (base + delta).replace(second=0, microsecond=0)

        if "day after tomorrow" in text:
            day = base.date() + timedelta(days=2)
        elif "tomorrow" in text:
            day = base.date() + timedelta(days=1)
        elif "tonight" in text:
            day, clock = base.date(), clock or time(20, 0)
        elif "today" in text or "tonight" in text:
            day = base.date()
        elif "next week" in text:
            day = base.date() + timedelta(days=7)
        else:
            for word, index in WEEKDAYS.items():
                if re.search(rf"\b{word}\b", text):
                    ahead = (index - base.weekday()) % 7 or 7
                    day = base.date() + timedelta(days=ahead)
                    break

    if day is None and clock is None:
        return None
    if day is None:
        day = base.date()
        candidate = datetime.combine(day, clock)
        if candidate < base:  # "at 6pm" said after 6pm means tomorrow
            day = day + timedelta(days=1)
    if clock is None:
        clock = time(9, 0)
    return datetime.combine(day, clock)


def humanise(dt: datetime | None, *, tz: str = "Asia/Kolkata") -> str:
    """Short, human-friendly rendering used by the mock provider and the UI."""
    if dt is None:
        return "no due date"
    base = now_local(tz)
    days = (dt.date() - base.date()).days
    label = {0: "today", 1: "tomorrow", -1: "yesterday"}.get(days)
    stamp = dt.strftime("%-I:%M %p") if dt.time() != time(0, 0) else ""
    if label:
        return f"{label} {stamp}".strip()
    if 0 < days < 7:
        return f"{dt.strftime('%A')} {stamp}".strip()
    return f"{dt.strftime('%-d %b %Y')} {stamp}".strip()
