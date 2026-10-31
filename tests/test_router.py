from __future__ import annotations

import pytest

from daytoday.router import route


@pytest.mark.parametrize("message,tool", [
    ("remind me to call the guide by friday", "add_task"),
    ("add task pay the electricity bill", "add_task"),
    ("i spent 420 on groceries", "add_expense"),
    ("paid 899 for the broadband renewal", "add_expense"),
    ("how much did i spend this month", "spending_summary"),
    ("show my recent transactions", "list_expenses"),
    ("what are my pending tasks", "list_tasks"),
    ("i finished the dbms numericals", "complete_task"),
    ("plan my day", "plan_day"),
    ("how have i been feeling", "mood_trend"),
    ("review my week", "weekly_review"),
    ("note that the guide meeting moved to cabin 214", "add_note"),
    ("what did i write about normalisation", "search_notes"),
])
def test_intent_routing(message, tool):
    calls = route(message)
    assert calls and calls[0].name == tool


def test_task_time_is_split_from_title():
    call = route("remind me to submit the synopsis by friday 5pm")[0]
    assert "synopsis" in call.arguments["title"]
    assert "friday" in call.arguments["when"]
    assert "friday" not in call.arguments["title"]


def test_amount_is_extracted():
    call = route("i spent 1.2k on a new chair")[0]
    assert call.arguments["amount"] == "1.2k"


def test_urgent_keyword_raises_priority():
    assert route("remind me to submit the viva report tomorrow")[0].arguments["priority"] == "high"
