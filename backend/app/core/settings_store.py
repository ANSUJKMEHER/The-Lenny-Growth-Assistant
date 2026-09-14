"""Runtime settings store (model toggle persisted in PostgreSQL).

Environment variables provide safe defaults; the user can override provider and
model at runtime via ``PUT /api/config``. Those overrides are written here and
survive restarts without any code change.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Provider, get_settings
from app.models import AppSetting

logger = logging.getLogger("app.settings_store")

_PROVIDER_KEY = "llm.provider"
_MODEL_KEY = "llm.model"


async def get_runtime_provider(db: AsyncSession) -> Provider:
    """Return the provider override, falling back to env config."""
    row = await db.get(AppSetting, _PROVIDER_KEY)
    if row and row.value:
        try:
            return Provider(row.value)
        except ValueError:
            logger.warning("Ignoring invalid stored provider %r", row.value)
    return get_settings().llm_provider


async def get_runtime_model(db: AsyncSession, provider: Provider) -> str:
    """Return the model override for a provider, falling back to env default."""
    key = f"{_MODEL_KEY}.{provider.value}"
    row = await db.get(AppSetting, key)
    if row and row.value:
        return row.value
    settings = get_settings()
    defaults = {
        Provider.OLLAMA: settings.ollama_model,
        Provider.ANTHROPIC: settings.anthropic_model,
        Provider.OPENAI: settings.openai_model,
    }
    return defaults[provider]


async def set_runtime_provider(db: AsyncSession, provider: Provider) -> None:
    db.add(AppSetting(key=_PROVIDER_KEY, value=provider.value))


async def set_runtime_model(db: AsyncSession, provider: Provider, model: str) -> None:
    db.add(AppSetting(key=f"{_MODEL_KEY}.{provider.value}", value=model))
