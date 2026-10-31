from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYTODAY_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("DAYTODAY_LLM_PROVIDER", "mock")
    import daytoday.agent
    import daytoday.api
    import daytoday.config
    import daytoday.db
    for module in (daytoday.config, daytoday.db, daytoday.agent, daytoday.api):
        importlib.reload(module)
    with TestClient(daytoday.api.app) as test_client:
        yield test_client


def test_health_reports_provider(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["provider"] == "mock"


def test_chat_roundtrip(client):
    body = client.post("/api/chat", json={"message": "remind me to buy a charger tomorrow",
                                         "session_id": "s1"}).json()
    assert "charger" in body["reply"]
    assert body["tool_calls"][0]["name"] == "add_task"


def test_task_created_from_ui_is_audited(client):
    created = client.post("/api/tasks", json={"title": "ui task", "priority": "high"})
    assert created.status_code == 201
    listed = client.get("/api/tasks").json()
    assert any(task["title"] == "ui task" for task in listed["tasks"])
    assert client.get("/api/metrics").json()["tool_calls"] >= 1


def test_bad_expense_amount_is_422(client):
    response = client.post("/api/expenses", json={"amount": "lots of money", "note": "x"})
    assert response.status_code == 422


def test_plan_endpoint(client):
    client.post("/api/tasks", json={"title": "something"})
    body = client.get("/api/plan").json()
    assert "blocks" in body and body["date_human"] == "today"


def test_notes_search_endpoint(client):
    client.post("/api/notes", json={"title": "OS notes",
                                    "body": "Deadlock requires mutual exclusion, hold and wait."})
    hits = client.get("/api/notes/search", params={"q": "deadlock"}).json()["hits"]
    assert hits and hits[0]["title"] == "OS notes"


def test_index_page_served(client):
    response = client.get("/")
    assert response.status_code == 200 and "DayToDay" in response.text
