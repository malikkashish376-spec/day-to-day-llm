"""Expense logging and spend analytics."""
from __future__ import annotations

import re
import sqlite3
from datetime import timedelta
from typing import Any

from ..config import settings
from ..db import utcnow
from ..formatting import fmt_money
from ..timeparse import now_local, parse_when
from .registry import Tool, ToolError

CATEGORY_RULES: dict[str, tuple[str, ...]] = {
    "food": ("coffee", "chai", "tea", "lunch", "dinner", "breakfast", "swiggy", "zomato",
             "restaurant", "cafe", "pizza", "snack", "mess", "canteen", "food"),
    "groceries": ("grocery", "groceries", "vegetables", "bigbasket", "dmart", "milk", "ration"),
    "transport": ("uber", "ola", "auto", "rickshaw", "metro", "bus", "train", "petrol",
                  "diesel", "fuel", "cab", "flight", "toll"),
    "bills": ("electricity", "water bill", "wifi", "broadband", "recharge", "rent",
              "insurance", "gas cylinder", "bill"),
    "education": ("book", "course", "udemy", "coursera", "exam", "fee", "college", "stationery",
                  "printout", "xerox"),
    "health": ("medicine", "pharmacy", "doctor", "hospital", "gym", "dentist", "chemist"),
    "shopping": ("amazon", "flipkart", "myntra", "clothes", "shoes", "headphones", "gadget"),
    "entertainment": ("movie", "netflix", "spotify", "concert", "game", "outing", "ticket"),
}

_AMOUNT_RE = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s*(k|thousand)?", re.IGNORECASE)


def parse_amount(value: Any) -> int:
    """Convert '250', '1.2k', 'Rs 1,450.50' into integer paise."""
    text = str(value).lower().replace(",", "").replace("\u20b9", "").replace("rs.", "")
    text = text.replace("rs", "").replace("inr", "").replace("$", "").strip()
    if text.strip().startswith("-") or " -" in text:
        raise ToolError("amount cannot be negative")
    match = _AMOUNT_RE.search(text)
    if not match:
        raise ToolError(f"could not read an amount from {value!r}")
    amount = float(match.group(1))
    if match.group(2):
        amount *= 1000
    minor = int(round(amount * 100))
    if minor <= 0:
        raise ToolError("amount must be greater than zero")
    if minor > 10_000_000_00:
        raise ToolError("amount looks implausible; please confirm the figure")
    return minor


def infer_category(note: str, fallback: str = "other") -> str:
    text = note.lower()
    for category, keywords in CATEGORY_RULES.items():
        if any(word in text for word in keywords):
            return category
    return fallback


def add_expense(conn: sqlite3.Connection, *, session_id: str, amount: Any,
                note: str = "", category: str | None = None,
                when: str | None = None) -> dict[str, Any]:
    minor = parse_amount(amount)
    note = (note or "").strip() or "unspecified"
    category = (category or "").lower() or infer_category(note)
    spent = parse_when(when) or now_local()
    conn.execute(
        "INSERT INTO expenses (amount_minor, currency, category, note, spent_on, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (minor, settings.currency, category, note, spent.date().isoformat(), utcnow()),
    )
    return {"ok": True, "amount": fmt_money(minor, settings.currency), "category": category,
            "note": note, "spent_on": spent.date().isoformat(),
            "message": f"Logged {fmt_money(minor, settings.currency)} on {category} ({note})."}


def _window(period: str) -> tuple[str, str]:
    today = now_local().date()
    period = (period or "month").lower()
    if period in ("today", "day"):
        start = today
    elif period in ("week", "7d"):
        start = today - timedelta(days=6)
    elif period in ("year", "all"):
        start = today - timedelta(days=3650)
    else:
        start = today.replace(day=1)
    return start.isoformat(), today.isoformat()


def spending_summary(conn: sqlite3.Connection, *, session_id: str,
                     period: str = "month") -> dict[str, Any]:
    start, end = _window(period)
    rows = list(conn.execute(
        "SELECT category, SUM(amount_minor) AS total, COUNT(*) AS n FROM expenses"
        " WHERE spent_on BETWEEN ? AND ? GROUP BY category ORDER BY total DESC",
        (start, end)))
    total = sum(row["total"] for row in rows)
    breakdown = [{"category": row["category"],
                  "total": fmt_money(row["total"], settings.currency),
                  "total_minor": row["total"],
                  "share_pct": round(100 * row["total"] / total, 1) if total else 0.0,
                  "count": row["n"]} for row in rows]
    top = breakdown[0]["category"] if breakdown else None
    return {"ok": True, "period": period, "from": start, "to": end,
            "total": fmt_money(total, settings.currency), "total_minor": total,
            "breakdown": breakdown, "top_category": top,
            "transaction_count": sum(row["n"] for row in rows)}


def list_expenses(conn: sqlite3.Connection, *, session_id: str,
                  limit: int = 10) -> dict[str, Any]:
    rows = list(conn.execute(
        "SELECT * FROM expenses ORDER BY spent_on DESC, id DESC LIMIT ?", (int(limit),)))
    return {"ok": True, "expenses": [
        {"id": row["id"], "amount": fmt_money(row["amount_minor"], row["currency"]),
         "category": row["category"], "note": row["note"], "spent_on": row["spent_on"]}
        for row in rows]}


TOOLS = [
    Tool(
        name="add_expense",
        description="Log money spent. Triggered by any statement of spending or payment.",
        parameters={
            "type": "object",
            "properties": {
                "amount": {"type": "string",
                           "description": "Amount as spoken: '250', '1.2k', 'Rs 1450'."},
                "note": {"type": "string", "description": "What the money was spent on."},
                "category": {"type": "string",
                             "description": "Optional; inferred from the note when omitted.",
                             "enum": sorted(list(CATEGORY_RULES) + ["other"])},
                "when": {"type": "string", "description": "Date phrase, e.g. 'yesterday'."},
            },
            "required": ["amount"],
        },
        handler=add_expense,
    ),
    Tool(
        name="spending_summary",
        description="Totals and category breakdown of spending for a period.",
        parameters={
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["today", "week", "month", "year"]},
            },
        },
        handler=spending_summary,
    ),
    Tool(
        name="list_expenses",
        description="Show the most recent individual transactions.",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
        handler=list_expenses,
    ),
]
