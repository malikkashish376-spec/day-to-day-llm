"""Central configuration for the DayToDay-LLM runtime.

All values come from environment variables so that the same image can be
deployed for the demo, the evaluation harness and the graded viva run.
Nothing in the codebase reads ``os.environ`` directly except this module.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value == "" else value


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    db_path: Path = PROJECT_ROOT / "data" / "daytoday.db"

    # --- LLM backend -------------------------------------------------------
    llm_provider: str = "mock"          # mock | ollama | openai
    llm_model: str = "llama3.1:8b"
    llm_temperature: float = 0.2
    ollama_host: str = "http://localhost:11434"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    request_timeout_s: int = 60

    # --- Agent behaviour ---------------------------------------------------
    max_tool_rounds: int = 4
    retrieval_k: int = 4
    memory_window: int = 8              # turns kept verbatim in the prompt

    # --- Locale ------------------------------------------------------------
    currency: str = "INR"
    timezone: str = "Asia/Kolkata"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(_env("DAYTODAY_DB", str(cls.db_path))),
            llm_provider=_env("DAYTODAY_LLM_PROVIDER", "mock").lower(),
            llm_model=_env("DAYTODAY_LLM_MODEL", "llama3.1:8b"),
            llm_temperature=float(_env("DAYTODAY_LLM_TEMPERATURE", "0.2")),
            ollama_host=_env("OLLAMA_HOST", "http://localhost:11434"),
            openai_base_url=_env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_api_key=_env("OPENAI_API_KEY", ""),
            openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
            request_timeout_s=_env_int("DAYTODAY_TIMEOUT_S", 60),
            max_tool_rounds=_env_int("DAYTODAY_MAX_TOOL_ROUNDS", 4),
            retrieval_k=_env_int("DAYTODAY_RETRIEVAL_K", 4),
            memory_window=_env_int("DAYTODAY_MEMORY_WINDOW", 8),
            currency=_env("DAYTODAY_CURRENCY", "INR"),
            timezone=_env("DAYTODAY_TIMEZONE", "Asia/Kolkata"),
        )


settings = Settings.from_env()
