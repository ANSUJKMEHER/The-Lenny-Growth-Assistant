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

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_timeout_seconds: float = 120.0

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
