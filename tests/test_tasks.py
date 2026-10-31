from __future__ import annotations

from datetime import timedelta

from daytoday.timeparse import now_local


def test_add_task_stores_due_date(registry, conn):
    result = registry.execute("add_task",
                              {"title": "submit synopsis", "when": "tomorrow 6pm",
                               "priority": "high"}, conn)
    assert result["ok"] is True
    row = conn.execute("SELECT * FROM tasks").fetchone()
    assert row["title"] == "submit synopsis"
    assert row["priority"] == "high"
    assert row["due_at"].startswith((now_local() + timedelta(days=1)).date().isoformat())


def test_add_task_without_due_date(registry, conn):
    result = registry.execute("add_task", {"title": "buy charger"}, conn)
    assert result["task"]["due_human"] == "no due date"


def test_list_flags_overdue(registry, conn):
    past = (now_local() - timedelta(days=2)).isoformat()
    conn.execute("INSERT INTO tasks (title, due_at, priority, status, tags, created_at)"
                 " VALUES ('late thing', ?, 'normal', 'open', '', '2026-01-01')", (past,))
    conn.commit()
    data = registry.execute("list_tasks", {"status": "open"}, conn)
    assert data["overdue_ids"]


def test_complete_task_fuzzy_match(registry, conn):
    registry.execute("add_task", {"title": "finish DBMS unit 3 numericals"}, conn)
    result = registry.execute("complete_task", {"query": "dbms numericals"}, conn)
    assert result["ok"] is True
    assert conn.execute("SELECT status FROM tasks").fetchone()["status"] == "done"


def test_complete_task_reports_miss(registry, conn):
    registry.execute("add_task", {"title": "renew broadband"}, conn)
    result = registry.execute("complete_task", {"query": "unrelated thing entirely"}, conn)
    assert result["ok"] is False and "no open task matched" in result["error"]


def test_invalid_priority_falls_back_to_normal(registry, conn):
    result = registry.execute("add_task", {"title": "x", "priority": "urgent!!"}, conn)
    assert result["task"]["priority"] == "normal"


def test_missing_required_argument_is_rejected(registry, conn):
    result = registry.execute("add_task", {}, conn)
    assert result["ok"] is False and "missing required" in result["error"]
