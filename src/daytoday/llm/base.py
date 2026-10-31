"""Provider-neutral LLM interface.

Every backend (local Ollama, any OpenAI-compatible endpoint, and the
deterministic mock used for tests and offline demos) is reduced to a single
``chat`` coroutine over a neutral message format. The agent loop never knows
which provider it is talking to, which is what makes the evaluation harness
able to compare a 3B local model against a hosted model on identical inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = "call_0"


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] | None = None

    @property
    def wants_tool(self) -> bool:
        return bool(self.tool_calls)


class LLMClient(Protocol):
    name: str

    async def chat(self, messages: list[dict[str, Any]],
                   tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        ...


class LLMError(RuntimeError):
    """Raised when a provider is unreachable or returns an unusable payload."""
