"""The agent loop.

One turn is: build the prompt (system + rolling summary + recent turns +
retrieved notes) -> ask the provider -> execute any tool calls -> feed the
results back -> repeat until the model answers in prose or the round budget
is exhausted. Every tool execution is audited with its latency, which is what
the metrics endpoint and the evaluation harness read.

Failure policy: a provider that is down does not break the assistant. The
loop degrades to the deterministic router for that turn and says so in the
response, because a personal assistant that stops working when the network
hiccups is not useful.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import memory, rag
from .config import Settings, settings as default_settings
from .db import connect, init_db
from .llm import LLMError, get_client
from .llm.base import LLMClient
from .llm.mock import MockLLM, render
from .timeparse import now_local
from .tools import build_registry
from .tools.registry import ToolRegistry

SYSTEM_PROMPT = """You are DayToDay, a private assistant for one person's everyday life: \
their tasks, spending, mood and notes. You are not a general chatbot.

Today is {date} ({weekday}); the current local time is {time} ({tz}). \
The user's currency is {currency}.

Operating rules:
- Any fact about the user's life must come from a tool result. Never invent a \
task, an amount, a date or a note that a tool did not return.
- Pass relative date phrases through unchanged in the `when` field \
("tomorrow 6pm", "by Friday"). The server resolves them; do not do date \
arithmetic yourself.
- Prefer one tool call per step when calls depend on each other; batch \
independent calls in a single turn.
- After a tool returns, answer in prose from its output: at most four \
sentences unless the user asks for detail. Summarise, never dump JSON.
- Format money in {currency} with Indian digit grouping (1,23,456.00).
- If a tool returns an error, say plainly what failed and what you need from \
the user. Do not retry the same call with identical arguments.
- If the notes have nothing relevant, say so instead of guessing.
- Be warm and brief. No motivational filler, no emoji.
"""


@dataclass
class ToolTrace:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    latency_ms: int = 0


@dataclass
class AgentResult:
    reply: str
    session_id: str
    provider: str
    tool_calls: list[ToolTrace] = field(default_factory=list)
    latency_ms: int = 0
    rounds: int = 0
    degraded: bool = False
    retrieved: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "session_id": self.session_id,
            "provider": self.provider,
            "latency_ms": self.latency_ms,
            "rounds": self.rounds,
            "degraded": self.degraded,
            "tool_calls": [
                {"name": t.name, "arguments": t.arguments,
                 "result": t.result, "latency_ms": t.latency_ms}
                for t in self.tool_calls
            ],
            "retrieved": self.retrieved,
        }


class Agent:
    def __init__(self, client: LLMClient | None = None,
                 registry: ToolRegistry | None = None,
                 config: Settings | None = None,
                 db_path: str | None = None) -> None:
        self.config = config or default_settings
        self.db_path = db_path or str(self.config.db_path)
        init_db(self.db_path)
        self.client = client or get_client(self.config)
        self.registry = registry or build_registry()
        self._fallback = MockLLM()

    # -- prompt ------------------------------------------------------------
    def _system_prompt(self) -> str:
        now = now_local(self.config.timezone)
        return SYSTEM_PROMPT.format(
            date=now.strftime("%d %B %Y"),
            weekday=now.strftime("%A"),
            time=now.strftime("%H:%M"),
            tz=self.config.timezone,
            currency=self.config.currency,
        )

    def _build_messages(self, conn, session_id: str, message: str,
                        retrieved: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt()}]
        summary = memory.latest_summary(conn, session_id)
        if summary:
            messages.append({"role": "system", "content": f"Session so far: {summary}"})
        if retrieved:
            messages.append({"role": "system", "content": retrieved})
        messages.extend(memory.recent(conn, session_id, self.config.memory_window))
        messages.append({"role": "user", "content": message})
        return messages

    # -- main entry point --------------------------------------------------
    async def respond(self, message: str, session_id: str = "default") -> AgentResult:
        started = time.perf_counter()
        message = (message or "").strip()
        if not message:
            return AgentResult(reply="Ask me anything about your day.", session_id=session_id,
                               provider=getattr(self.client, "name", "unknown"))

        conn = connect(self.db_path)
        traces: list[ToolTrace] = []
        degraded = False
        rounds = 0
        try:
            memory.record(conn, session_id, "user", message)
            context = rag.build_context(conn, message, k=self.config.retrieval_k)
            messages = self._build_messages(conn, session_id, message, context)
            retrieved = rag.search_notes(conn, message, k=self.config.retrieval_k)

            client: LLMClient = self.client
            reply = ""
            while rounds < self.config.max_tool_rounds:
                rounds += 1
                try:
                    response = await client.chat(messages, self.registry.schemas())
                except LLMError:
                    if client is self._fallback:
                        raise
                    degraded, client = True, self._fallback
                    response = await client.chat(messages, self.registry.schemas())

                if not response.wants_tool:
                    reply = response.text.strip()
                    break

                messages.append({
                    "role": "assistant",
                    "content": response.text or "",
                    "tool_calls": [
                        {"id": call.id, "type": "function",
                         "function": {"name": call.name,
                                      "arguments": json.dumps(call.arguments, ensure_ascii=False)}}
                        for call in response.tool_calls
                    ],
                })
                for call in response.tool_calls:
                    result = self.registry.execute(call.name, call.arguments, conn, session_id)
                    latency = conn.execute(
                        "SELECT latency_ms FROM tool_audit ORDER BY id DESC LIMIT 1"
                    ).fetchone()["latency_ms"]
                    traces.append(ToolTrace(call.name, call.arguments, result, latency))
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    })

            if not reply:
                # Round budget exhausted, or the provider returned empty prose:
                # answer from whatever the tools produced rather than nothing.
                reply = render([(trace.name, trace.result) for trace in traces]) if traces else \
                    "I could not finish that in the allowed steps. Try rephrasing, or ask for one thing at a time."

            memory.record(conn, session_id, "assistant", reply)
            return AgentResult(
                reply=reply, session_id=session_id, provider=client.name,
                tool_calls=traces,
                latency_ms=int((time.perf_counter() - started) * 1000),
                rounds=rounds, degraded=degraded, retrieved=retrieved,
            )
        finally:
            conn.close()

    # -- reporting ---------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS calls, AVG(latency_ms) AS mean_ms,"
                " SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS errors FROM tool_audit").fetchone()
            by_tool = [dict(r) for r in conn.execute(
                "SELECT tool, COUNT(*) AS calls, ROUND(AVG(latency_ms),1) AS mean_ms"
                " FROM tool_audit GROUP BY tool ORDER BY calls DESC")]
            counts = {
                "tasks_open": conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='open'").fetchone()["c"],
                "expenses": conn.execute("SELECT COUNT(*) c FROM expenses").fetchone()["c"],
                "journal": conn.execute("SELECT COUNT(*) c FROM journal").fetchone()["c"],
                "notes": conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"],
                "note_chunks": conn.execute("SELECT COUNT(*) c FROM note_chunks").fetchone()["c"],
            }
            return {
                "provider": getattr(self.client, "name", "unknown"),
                "model": self.config.llm_model,
                "tool_calls": row["calls"],
                "tool_error_rate": round((row["errors"] or 0) / row["calls"], 3) if row["calls"] else 0.0,
                "mean_tool_latency_ms": round(row["mean_ms"], 1) if row["mean_ms"] else 0.0,
                "per_tool": by_tool,
                "records": counts,
                "server_time": datetime.now().isoformat(timespec="seconds"),
            }
        finally:
            conn.close()
