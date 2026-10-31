"""Local inference through an Ollama server (default for the project demo).

Running the assistant against a local 8B model is what makes this project a
*personal* assistant: no personal journal or expense data leaves the machine.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from .base import LLMError, LLMResponse, ToolCall


class OllamaClient:
    name = "ollama"

    def __init__(self, host: str, model: str, temperature: float = 0.2,
                 timeout: int = 60) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    async def chat(self, messages: list[dict[str, Any]],
                   tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if tools:
            payload["tools"] = tools
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.host}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:  # network, 404 model-not-pulled, etc.
            raise LLMError(f"Ollama request failed: {exc}") from exc

        message = data.get("message", {})
        calls = [
            ToolCall(
                name=call["function"]["name"],
                arguments=call["function"].get("arguments") or {},
                id=f"call_{index}",
            )
            for index, call in enumerate(message.get("tool_calls") or [])
        ]
        return LLMResponse(text=message.get("content", "") or "", tool_calls=calls, raw=data)

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                return (await client.get(f"{self.host}/api/tags")).status_code == 200
        except httpx.HTTPError:
            return False
