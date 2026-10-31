"""Presentation helpers shared by the API, the CLI and the mock provider."""
from __future__ import annotations

CURRENCY_SYMBOLS = {"INR": "\u20b9", "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3"}


def fmt_money(amount_minor: int, currency: str = "INR") -> str:
    symbol = CURRENCY_SYMBOLS.get(currency, currency + " ")
    whole, minor = divmod(abs(int(amount_minor)), 100)
    sign = "-" if amount_minor < 0 else ""
    # Indian digit grouping: 1,23,456.00
    text = str(whole)
    if len(text) > 3:
        head, tail = text[:-3], text[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        text = ",".join(groups) + "," + tail
    return f"{sign}{symbol}{text}.{minor:02d}"


def truncate(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "\u2026"
