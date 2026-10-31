"""Tool registry: JSON-schema descriptions plus validated dispatch.

The registry is the single source of truth for what the assistant can do.
Tool schemas are exported in OpenAI function-calling format and are also what
the rule-based fallback and the evaluation harness read, so capability,
prompting and testing can never drift apart.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Callable

from ..db import utcnow


class ToolError(Exception):
    """Recoverable failure: reported back to the model, never crashes the loop."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool {tool.name}")
        self._tools[tool.name] = tool

    def tool(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolError(f"unknown tool '{name}'. Available: {', '.join(sorted(self._tools))}")
        return self._tools[name]

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        return [self._tools[name].schema() for name in self.names]

    def execute(self, name: str, arguments: dict[str, Any],
                conn: sqlite3.Connection, session_id: str = "default") -> dict[str, Any]:
        """Run one tool call, audit it, and return a JSON-safe result dict."""
        tool = self.tool(name)
        started = time.perf_counter()
        ok = 1
        try:
            args = _validate(tool, arguments or {})
            result = tool.handler(conn, session_id=session_id, **args)
        except ToolError as exc:
            ok, result = 0, {"ok": False, "error": str(exc)}
        except TypeError as exc:
            ok, result = 0, {"ok": False, "error": f"bad arguments for {name}: {exc}"}
        except Exception as exc:  # noqa: BLE001 - surfaced to the model, logged to audit
            ok, result = 0, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        latency = int((time.perf_counter() - started) * 1000)
        conn.execute(
            "INSERT INTO tool_audit (session_id, tool, arguments, result, ok, latency_ms, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (session_id, name, json.dumps(arguments, ensure_ascii=False),
             json.dumps(result, ensure_ascii=False, default=str), ok, latency, utcnow()),
        )
        conn.commit()
        return result


def _validate(tool: Tool, args: dict[str, Any]) -> dict[str, Any]:
    """Minimal JSON-schema validation.

    Models routinely omit optional keys, send numbers as strings and invent
    extra keys. We coerce what is safe, drop what is unknown and reject only
    a missing required argument -- strict validation here caused more failed
    tool calls than it prevented during development.
    """
    props: dict[str, Any] = tool.parameters.get("properties", {})
    required: list[str] = tool.parameters.get("required", [])
    clean: dict[str, Any] = {}
    for key, spec in props.items():
        if key in args and args[key] is not None and args[key] != "":
            value = args[key]
            kind = spec.get("type")
            if kind == "number":
                try:
                    value = float(str(value).replace(",", ""))
                except ValueError:
                    raise ToolError(f"'{key}' must be a number, got {value!r}")
                if spec.get("integer") or float(value).is_integer():
                    value = int(value)
            elif kind == "string":
                value = str(value)
            elif kind == "integer":
                try:
                    value = int(float(str(value)))
                except ValueError:
                    raise ToolError(f"'{key}' must be an integer, got {value!r}")
            clean[key] = value
    missing = [key for key in required if key not in clean]
    if missing:
        raise ToolError(f"missing required argument(s): {', '.join(missing)}")
    return clean
