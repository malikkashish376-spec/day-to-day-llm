"""Provider factory."""
from __future__ import annotations

from ..config import Settings, settings as default_settings
from .base import LLMClient, LLMError, LLMResponse, ToolCall
from .ollama import OllamaClient
from .openai_compat import OpenAICompatibleClient

__all__ = ["get_client", "LLMClient", "LLMError", "LLMResponse", "ToolCall"]


def get_client(config: Settings | None = None) -> LLMClient:
    config = config or default_settings
    provider = config.llm_provider
    if provider == "ollama":
        return OllamaClient(config.ollama_host, config.llm_model,
                            config.llm_temperature, config.request_timeout_s)
    if provider in ("openai", "openai_compatible", "groq", "together"):
        return OpenAICompatibleClient(config.openai_base_url, config.openai_api_key,
                                      config.openai_model, config.llm_temperature,
                                      config.request_timeout_s)
    # Imported lazily: the mock provider imports the intent router, which
    # imports this package. A top-level import here would close that cycle.
    from .mock import MockLLM
    return MockLLM()
