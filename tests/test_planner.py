from __future__ import annotations

from datetime import datetime

from daytoday.timeparse import now_local


def test_plan_never_schedules_in_the_past(registry, conn):
    registry.execute("add_task", {"title": "task one"}, conn)
    data = registry.execute("plan_day", {"when": "today"}, conn)
    first = datetime.fromisoformat(f"{now_local().date()}T{data['blocks'][0]['start']}")
    assert first >= now_local().replace(second=0, microsecond=0)


def test_plan_orders_overdue_first(registry, conn):
    past = (now_local().replace(hour=9, minute=0) - __import__("datetime").timedelta(days=3)).isoformat()
    conn.execute("INSERT INTO tasks (title, due_at, priority, status, tags, created_at)"
                 " VALUES ('overdue thing', ?, 'normal', 'open', '', '2026-01-01')", (past,))
    registry.execute("add_task", {"title": "future thing", "when": "in 5 days"}, conn)
    data = registry.execute("plan_day", {"when": "today"}, conn)
    assert data["blocks"][0]["title"] == "overdue thing"
    assert data["blocks"][0]["flag"] == "overdue"


def test_plan_caps_blocks_and_reports_rest(registry, conn):
    for index in range(9):
        registry.execute("add_task", {"title": f"task {index}"}, conn)
    data = registry.execute("plan_day", {"when": "today"}, conn)
    assert len(data["blocks"]) == 6
    assert len(data["unscheduled"]) == 3


def test_empty_day_gives_coach_note(registry, conn):
    data = registry.execute("plan_day", {"when": "today"}, conn)
    assert data["blocks"] == [] and data["coach_note"]


def test_weekly_review_shape(registry, conn):
    registry.execute("add_expense", {"amount": "300", "note": "lunch"}, conn)
    data = registry.execute("weekly_review", {}, conn)
    assert data["ok"] and data["spend_this_week"].startswith("\u20b9")
