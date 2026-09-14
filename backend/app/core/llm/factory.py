"""Provider factory and fallback resolution.

``build_provider`` constructs a provider from a name (+ optional model).
``resolve_provider`` applies the configured fallback chain when the requested
provider is unavailable, so the demo degrades gracefully instead of hard
failing when, for example, Ollama isn't running.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Provider, get_settings
from app.core import settings_store
from app.core.llm.anthropic import AnthropicProvider
from app.core.llm.base import LLMProvider, ProviderError
from app.core.llm.ollama import OllamaProvider
from app.core.llm.openai import OpenAIProvider

logger = logging.getLogger("app.llm.factory")

# Preferred fallback order: local first (free, keyless), then cloud.
FALLBACK_ORDER: list[Provider] = [Provider.OLLAMA, Provider.ANTHROPIC, Provider.OPENAI]


def build_provider(provider: Provider, model: str | None = None) -> LLMProvider:
    """Construct a provider instance. Raises ``ProviderError`` if unconfigured."""
    settings = get_settings()
    if provider is Provider.OLLAMA:
        return OllamaProvider(
            settings.ollama_base_url,
            model or settings.ollama_model,
            timeout=settings.ollama_timeout_seconds,
        )
    if provider is Provider.ANTHROPIC:
        if not settings.anthropic_api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        return AnthropicProvider(
            settings.anthropic_api_key,
            model or settings.anthropic_model,
            settings.anthropic_base_url,
        )
    if provider is Provider.OPENAI:
        if not settings.openai_api_key:
            raise ProviderError("OPENAI_API_KEY is not set")
        return OpenAIProvider(
            settings.openai_api_key,
            model or settings.openai_model,
            settings.openai_base_url,
        )
    raise ProviderError(f"Unknown provider: {provider}")


async def resolve_provider(
    db: AsyncSession, requested: Provider | None = None
) -> LLMProvider:
    """Resolve an LLM provider, applying fallback if enabled.

    Returns the first provider that both is configured and passes a lightweight
    healthcheck. Raises ``ProviderError`` if none are available.
    """
    settings = get_settings()
    order: list[Provider] = []
    if requested is not None:
        order.append(requested)
        order += [p for p in FALLBACK_ORDER if p is not requested]
    else:
        active = await settings_store.get_runtime_provider(db)
        order.append(active)
        order += [p for p in FALLBACK_ORDER if p is not active]

    errors: list[str] = []
    for provider in order:
        model = await settings_store.get_runtime_model(db, provider)
        try:
            instance = build_provider(provider, model)
        except ProviderError as exc:
            errors.append(f"{provider.value}: {exc}")
            continue

        if not settings.llm_fallback_enabled and provider is not order[0]:
            # Fallback disabled: only the requested provider is tried.
            break

        ok, reason = await instance.healthcheck()
        if ok:
            if provider is not order[0]:
                logger.warning("Falling back from %s to %s", order[0].value, provider.value)
            return instance
        errors.append(f"{provider.value}: {reason or 'healthcheck failed'}")

    raise ProviderError("No LLM provider available. " + "; ".join(errors))
