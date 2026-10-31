from __future__ import annotations

import pytest

from daytoday.tools.expenses import infer_category, parse_amount


@pytest.mark.parametrize("value,expected", [
    ("250", 25000), ("Rs 1,450.50", 145050), ("1.2k", 120000),
    ("\u20b980", 8000), ("0.5", 50),
])
def test_parse_amount(value, expected):
    assert parse_amount(value) == expected


@pytest.mark.parametrize("value", ["", "lots", "0", "-5"])
def test_parse_amount_rejects_nonsense(value):
    with pytest.raises(Exception):
        parse_amount(value)


@pytest.mark.parametrize("note,category", [
    ("auto to college", "transport"), ("canteen lunch", "food"),
    ("dbms textbook", "education"), ("netflix", "entertainment"),
    ("something odd", "other"),
])
def test_category_inference(note, category):
    assert infer_category(note) == category


def test_summary_totals_match_rows(registry, conn):
    for amount in ("100", "250.50", "49.50"):
        registry.execute("add_expense", {"amount": amount, "note": "chai"}, conn)
    data = registry.execute("spending_summary", {"period": "month"}, conn)
    rows_total = conn.execute("SELECT SUM(amount_minor) t FROM expenses").fetchone()["t"]
    assert data["total_minor"] == rows_total == 40000
    assert data["breakdown"][0]["share_pct"] == 100.0


def test_amount_stored_in_minor_units(registry, conn):
    registry.execute("add_expense", {"amount": "199.99", "note": "book"}, conn)
    assert conn.execute("SELECT amount_minor FROM expenses").fetchone()["amount_minor"] == 19999
