"""Any OpenAI-compatible chat-completions endpoint.

Works unchanged for OpenAI, Groq, Together, vLLM, LM Studio and Ollama's own
``/v1`` shim, so the graded demo can fall back to a hosted model on a laptop
that cannot run a local one.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from .base import LLMError, LLMResponse, ToolCall


class OpenAICompatibleClient:
    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str,
                 temperature: float = 0.2, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    async def chat(self, messages: list[dict[str, Any]],
                   tools: list[dict[str, Any]] | None = None) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/chat/completions",
                                             json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenAI-compatible request failed: {exc}") from exc

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        calls: list[ToolCall] = []
        for index, call in enumerate(message.get("tool_calls") or []):
            raw_args = call.get("function", {}).get("arguments") or "{}"
            try:
                parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                parsed = {}
            calls.append(ToolCall(name=call["function"]["name"], arguments=parsed,
                                  id=call.get("id", f"call_{index}")))
        return LLMResponse(text=message.get("content") or "", tool_calls=calls, raw=data)
