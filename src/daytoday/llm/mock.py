"""Deterministic provider: no network, no weights, no API key.

It runs the same agent loop as a real model -- route, call tools, then answer
from the tool output -- so the application, the tests and the demo all
exercise production code paths. Answers are rendered from real database rows,
never invented, which is also what makes it a useful reference for
groundedness: any phrasing here that a real model cannot match is a prompt bug.
"""
from __future__ import annotations

import json
from typing import Any

from ..router import route
from .base import LLMResponse, ToolCall


def _tool_payloads(messages: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    payloads = []
    for message in reversed(messages):
        if message.get("role") == "user":
            break
        if message.get("role") == "tool":
            try:
                payloads.append((message.get("name", ""), json.loads(message.get("content", "{}"))))
            except json.JSONDecodeError:
                payloads.append((message.get("name", ""), {"error": "unreadable tool output"}))
    return list(reversed(payloads))


def _bullets(items: list[str], limit: int = 6) -> str:
    shown = items[:limit]
    text = "; ".join(shown)
    if len(items) > limit:
        text += f"; and {len(items) - limit} more"
    return text


def render(payloads: list[tuple[str, dict[str, Any]]]) -> str:
    if not payloads:
        return ("I can track tasks, expenses, journal entries and your notes. "
                "Try: 'remind me to submit the synopsis by Friday'.")
    chunks: list[str] = []
    for name, data in payloads:
        if data.get("error"):
            chunks.append(f"I could not complete that: {data['error']}")
            continue
        if name == "add_task":
            task = data["task"]
            chunks.append(f"Added: {task['title']} ({task['due_human']}, {task['priority']} priority).")
        elif name == "list_tasks":
            if not data["count"]:
                chunks.append("Nothing is pending. Your list is clear.")
            else:
                parts = []
                for task in data["tasks"][:8]:
                    flag = " [overdue]" if task["id"] in data.get("overdue_ids", []) else ""
                    due = f" - {task['due_human']}" if task["due_human"] else ""
                    parts.append(f"#{task['id']} {task['title']}{due}{flag}")
                chunks.append(f"You have {data['count']} open task(s): " + _bullets(parts, 8) + ".")
        elif name == "complete_task":
            chunks.append(data["message"])
        elif name == "add_expense":
            chunks.append(data["message"])
        elif name == "spending_summary":
            if not data["transaction_count"]:
                chunks.append(f"No expenses recorded for this {data['period']} yet.")
            else:
                top = ", ".join(f"{row['category']} {row['total']} ({row['share_pct']}%)"
                                for row in data["breakdown"][:3])
                chunks.append(f"You spent {data['total']} this {data['period']} across "
                              f"{data['transaction_count']} transaction(s). Biggest: {top}.")
        elif name == "list_expenses":
            rows = [f"{row['spent_on']} {row['amount']} {row['category']} ({row['note']})"
                    for row in data["expenses"]]
            chunks.append("Recent spending: " + _bullets(rows, 8) + "." if rows
                          else "No transactions logged yet.")
        elif name == "log_journal":
            note = " (mood inferred from your text)" if data.get("mood_inferred") else ""
            chunks.append(f"Journal saved - mood {data['mood']}/5, energy {data['energy']}/5{note}.")
        elif name == "mood_trend":
            if not data.get("entries"):
                chunks.append("No journal entries yet, so there is no trend to report.")
            else:
                chunks.append(f"Across {data['entries']} entry(ies) your average mood is "
                              f"{data['average_mood']}/5 and energy {data['average_energy']}/5; "
                              f"the trend is {data.get('trend', 'unclear')}.")
        elif name == "add_note":
            chunks.append(data["message"])
        elif name == "search_notes":
            if not data["hits"]:
                chunks.append("I could not find anything in your notes about that.")
            else:
                hits = [f"{hit['title']} ({hit['created_at'][:10]}): "
                        f"{hit['snippet'].rstrip(' .')}" for hit in data["hits"]]
                chunks.append("From your notes - " + _bullets(hits, 3) + ".")
        elif name == "plan_day":
            if not data["blocks"]:
                chunks.append(f"No pending work for {data['date_human']}. {data['coach_note']}")
            else:
                blocks = [f"{b['start']}-{b['end']} {b['title']}" for b in data["blocks"]]
                chunks.append(f"Plan for {data['date_human']}: " + _bullets(blocks, 6) + ".")
                chunks.append(data["coach_note"])
        elif name == "weekly_review":
            change = ("no prior week to compare" if data["spend_change_pct"] is None
                      else f"{data['spend_change_pct']:+.1f}% vs last week")
            chunks.append(
                f"Last 7 days: {data['tasks_completed']} task(s) completed, "
                f"{data['tasks_open']} still open ({data['tasks_overdue']} overdue). "
                f"Spending {data['spend_this_week']} ({change})"
                + (f", mostly {data['top_category']}" if data["top_category"] else "")
                + (f". Average mood {data['average_mood']}/5." if data["average_mood"] else "."))
        else:
            chunks.append(json.dumps(data, ensure_ascii=False)[:300])
    return " ".join(chunks)


class MockLLM:
    name = "mock"

    async def chat(self, messages: list[dict[str, Any]],
                   tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        last = messages[-1] if messages else {"role": "user", "content": ""}
        if last.get("role") == "tool":
            return LLMResponse(text=render(_tool_payloads(messages)))
        user_text = last.get("content", "")
        calls: list[ToolCall] = route(user_text)
        if not calls:
            return LLMResponse(text=render([]))
        return LLMResponse(tool_calls=calls)
