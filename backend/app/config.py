"""Application configuration.

All configuration is driven by environment variables (with safe defaults) and
loaded once at startup. Runtime provider/model overrides are persisted to the
database (see :mod:`app.core.settings_store`) so a user can switch models from
the UI without touching code or restarting the process.
"""
from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(str, Enum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Database -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://lenny:lenny@localhost:5432/lenny"

    # --- LLM ----------------------------------------------------------------
    llm_provider: Provider = Provider.OLLAMA
    llm_fallback_enabled: bool = True

    # Agent runtime: "auto" (use Claude Agent SDK when the Anthropic provider
    # is active and the SDK+CLI are installed, else the built-in loop),
    # "claude_sdk" (require the SDK), or "builtin" (always the built-in loop).
    agent_runtime: str = "auto"
    # Optional path to the Claude Code CLI binary used by the Agent SDK.
    claude_cli_path: str = ""

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout_seconds: float = 120.0
    # How long Ollama keeps a model resident after use. "30m" keeps the model
    # loaded across the demo so the first request isn't repeatedly cold.
    ollama_keep_alive: str = "30m"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # --- Retrieval ----------------------------------------------------------
    embedding_dim: int = 768
    chunk_target_tokens: int = 400
    chunk_overlap_tokens: int = 80
    retrieval_top_k: int = 6

    # --- Application --------------------------------------------------------
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "*"
    log_level: str = "INFO"
    max_artifact_bytes: int = 262_144

    # When True, ``init_db`` creates tables at startup (dev/test convenience).
    # Production (Docker) sets this False and lets Alembic manage the schema.
    auto_create_tables: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str) and "," in v:
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        if isinstance(self.cors_origins, str):
            return [self.cors_origins]
        return self.cors_origins  # type: ignore[return-value]

    @property
    def anthropic_base_url(self) -> str:
        return "https://api.anthropic.com/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
