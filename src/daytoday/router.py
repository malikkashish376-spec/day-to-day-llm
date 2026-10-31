"""Deterministic intent router ("the reference policy").

This is the project's answer to a practical problem: an assistant that only
works when a GPU is available cannot be graded, tested in CI, or demoed on a
weak laptop. The router is a rule-based classifier over the same tool schemas
the LLM sees, and it serves three roles:

1. the offline/mock provider, so the whole system is demoable with no model;
2. the baseline in the evaluation harness, so LLM routing accuracy is
   measured against something honest;
3. a safety net in the agent loop -- if a provider returns prose when the
   message obviously requires data, the router can propose the call.

It is intentionally simple: ordered regex rules with slot extraction.
"""
from __future__ import annotations

import re
from typing import Any

from .llm.base import ToolCall

MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
TIME_HINT = (r"(today|tomorrow|tonight|yesterday|next week|day after tomorrow|"
             r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|"
             r"thu|thur|thurs|fri|sat|sun|at\s+\d{1,2}(:\d{2})?\s*(am|pm)?|"
             r"by\s+\d{1,2}(:\d{2})?\s*(am|pm)?|in\s+\d{1,3}\s*(min|mins|minutes|hours|hrs|days)|"
             r"\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?|\d{4}-\d{2}-\d{2}|by\s+" + MONTHS + ")")

TASK_VERBS = (r"(remind me to|add (a )?task|add to my (to-?do|list)|note down that i|"
              r"i need to|i have to|i must|put on my list|todo:?|gotta|gonna|"
              r"need to|have got to|i should|let'?s schedule)")
DONE_VERBS = r"(done with|finished|completed|i did|mark .* as done|cross off|tick off|completed)"
SPEND_VERBS = r"(spent|paid|bought|cost(s|ing)?( me)?|charged|expense of|shelled out|swiped)"


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" .!?,;"))


def _strip_lead(text: str, patterns: str) -> str:
    return _clean(re.sub(rf"^\s*(?:{patterns})\s*", "", text, flags=re.IGNORECASE))


def _split_time(text: str) -> tuple[str, str | None]:
    """Separate the task body from its trailing time expression."""
    match = re.search(rf"\b(by|before|at|on|due|till|until)\b\s*({TIME_HINT}.*)$", text,
                      flags=re.IGNORECASE)
    if match:
        body = text[: match.start()].strip(" ,.-")
        when = f"{match.group(1)} {match.group(2)}"
        return _clean(body), _clean(when)
    trailing = re.search(rf"\b({TIME_HINT})\s*$", text, flags=re.IGNORECASE)
    if trailing and trailing.start() > 0:
        return _clean(text[: trailing.start()]), _clean(trailing.group(1))
    return _clean(text), None


def _period(text: str) -> str:
    lowered = text.lower()
    if "today" in lowered:
        return "today"
    if "week" in lowered or "7 day" in lowered:
        return "week"
    if "year" in lowered or "all time" in lowered:
        return "year"
    return "month"


def _amount_and_note(text: str) -> tuple[str, str]:
    match = re.search(r"(?:rs\.?|inr|\u20b9|\$)?\s*(\d+(?:[.,]\d{1,2})?\s*(?:k|thousand)?)",
                      text, flags=re.IGNORECASE)
    amount = _clean(match.group(1)) if match else ""
    note = text
    if match:
        note = text[: match.start()] + " " + text[match.end():]
    for pattern in (r"(i|i'?ve|we|just|today|yesterday|also|then)", SPEND_VERBS,
                    r"(on|for|of|at|rs\.?|inr|\u20b9|bucks|rupees|dollars)"):
        note = _strip_lead(note, pattern)
    note = re.sub(r"^(i|we)\s+", "", note, flags=re.IGNORECASE)
    return amount, _clean(note) or "unspecified"


def route(text: str) -> list[ToolCall]:
    """Map one user utterance onto zero or more tool calls."""
    lowered = text.lower().strip()
    if not lowered:
        return []

    # --- analytics before logging, so "how much did I spend" is not logged ---
    if re.search(r"(how much|total|summary|breakdown|where did).*(spend|spent|expense|money)", lowered) \
            or "spending summary" in lowered or "budget" in lowered:
        return [ToolCall("spending_summary", {"period": _period(lowered)})]

    if re.search(r"(show|list|recent|last).*(expense|transaction|purchase|spending)", lowered):
        return [ToolCall("list_expenses", {"limit": 8})]

    if re.search(r"(how have i been|mood trend|my mood|how am i feeling|energy levels|"
                 r"(mood|energy).{0,20}(been like|this fortnight|lately|recently))", lowered):
        return [ToolCall("mood_trend", {"days": 14})]

    if re.search(r"(review my week|week in review|how was my week|weekly review|week summary|"
                 r"(summaris|summariz|summary of|recap of).{0,12}week)", lowered):
        return [ToolCall("weekly_review", {})]

    if re.search(r"(plan my day|what should i do (today|now)|schedule (my )?(today|day)|"
                 r"what'?s on my plate|my day|day plan|plan for tomorrow|"
                 r"(sort out|organis|organiz|structure|arrange)\w* (my )?(schedule|day))", lowered):
        when = "tomorrow" if "tomorrow" in lowered else "today"
        return [ToolCall("plan_day", {"when": when})]

    if re.search(rf"\b{DONE_VERBS}\b", lowered) or \
            re.search(r"\b(is|are|was|were)\s+(done|complete|completed|finished)\b", lowered):
        target = re.sub(rf"^\s*(i'?m\s+)?({DONE_VERBS})\s*", "", lowered)
        target = re.sub(r"^(with|the|my)\s+", "", target)
        return [ToolCall("complete_task", {"query": _clean(target)})]

    if re.search(r"(my tasks|my to-?do|what.*pending|what.*left|show.*tasks|pending tasks|"
                 r"what do i have|what'?s on my list|anything (pending|left|for today|on my))", lowered):
        return [ToolCall("list_tasks", {"status": "open"})]

    if re.search(rf"\b{SPEND_VERBS}\b", lowered) and re.search(r"\d", lowered):
        amount, note = _amount_and_note(text)
        return [ToolCall("add_expense", {"amount": amount, "note": note})]

    if re.search(rf"^\s*{TASK_VERBS}", lowered) or re.search(r"\bremind me\b", lowered) \
            or re.search(r"\b(put|add|stick)\b.{0,40}\b(on|to) my (plate|list)\b", lowered):
        body = _strip_lead(text, TASK_VERBS + r"|that|to")
        title, when = _split_time(body)
        args: dict[str, Any] = {"title": title or _clean(text)}
        if when:
            args["when"] = when
        if re.search(r"(urgent|important|asap|exam|deadline|interview|viva|submission)", lowered):
            args["priority"] = "high"
        return [ToolCall("add_task", args)]

    if re.search(r"(journal|log my day|today went|i feel|feeling|i'?m (so )?(tired|happy|stressed))",
                 lowered) and len(lowered.split()) >= 3:
        return [ToolCall("log_journal", {"entry": _clean(text)})]

    if re.search(r"^(note that|save this|remember that|note:|jot down)", lowered):
        return [ToolCall("add_note", {"body": _clean(re.sub(
            r"^(note that|save this|remember that|note:|jot down)\s*", "", text,
            flags=re.IGNORECASE))})]

    # Default: treat as a question about the user's own notes. Retrieval that
    # returns nothing is a better answer than a hallucinated one.
    query = _strip_lead(text, r"(what|when|where|who|how|do i|did i|tell me|do you remember|"
                              r"remind me|from my notes|in my notes|about)")
    return [ToolCall("search_notes", {"query": query or _clean(text)})]
