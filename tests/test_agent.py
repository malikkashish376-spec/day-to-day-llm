from __future__ import annotations

import asyncio

import pytest

from daytoday.agent import Agent
from daytoday.llm.base import LLMError, LLMResponse
from daytoday.llm.mock import MockLLM


def ask(agent: Agent, message: str, session: str = "t") -> dict:
    return asyncio.run(agent.respond(message, session)).to_dict()


def test_turn_produces_grounded_reply(agent):
    result = ask(agent, "i spent 250 on coffee")
    assert "250" in result["reply"]
    assert result["tool_calls"][0]["name"] == "add_expense"
    assert result["provider"] == "mock"


def test_multi_turn_memory_is_replayed(agent):
    ask(agent, "remind me to submit the synopsis by friday")
    result = ask(agent, "what are my pending tasks")
    assert "synopsis" in result["reply"]


def test_every_tool_call_is_audited(agent, db_path):
    from daytoday.db import connect
    ask(agent, "how much did i spend this month")
    conn = connect(db_path)
    rows = conn.execute("SELECT tool, ok, latency_ms FROM tool_audit").fetchall()
    conn.close()
    assert rows and rows[0]["tool"] == "spending_summary"
    assert rows[0]["ok"] == 1
    assert rows[0]["latency_ms"] >= 0


class BrokenClient:
    name = "broken"

    async def chat(self, messages, tools=None):
        raise LLMError("connection refused")


def test_provider_failure_degrades_instead_of_crashing(db_path):
    agent = Agent(client=BrokenClient(), db_path=db_path)
    result = ask(agent, "i spent 100 on lunch")
    assert result["degraded"] is True
    assert result["provider"] == "mock"
    assert "100" in result["reply"]


def test_empty_message_is_handled(agent):
    result = ask(agent, "   ")
    assert result["reply"] and result["tool_calls"] == []


def test_tool_error_is_reported_not_raised(agent):
    result = ask(agent, "i finished the quantum mechanics thesis")
    assert result["tool_calls"][0]["name"] == "complete_task"
    assert "could not" in result["reply"].lower() or "no open task" in result["reply"].lower()


def test_round_budget_is_bounded(db_path):
    class LoopingClient:
        name = "looper"

        async def chat(self, messages, tools=None):
            from daytoday.llm.base import ToolCall
            return LLMResponse(tool_calls=[ToolCall("list_tasks", {})])

    agent = Agent(client=LoopingClient(), db_path=db_path)
    result = asyncio.run(agent.respond("loop forever", "t"))
    assert result.rounds <= agent.config.max_tool_rounds
    assert result.reply  # never an empty answer
