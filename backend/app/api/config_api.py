"""Runtime configuration and provider toggle endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Provider, get_settings
from app.core import settings_store
from app.core.llm.base import ProviderError
from app.core.llm.factory import FALLBACK_ORDER, build_provider
from app.db import get_db
from app.schemas import ConfigOut, ConfigUpdate, ProviderInfo

router = APIRouter(prefix="/api/config", tags=["config"])


async def _provider_info(db: AsyncSession, provider: Provider) -> ProviderInfo:
    try:
        model = await settings_store.get_runtime_model(db, provider)
        inst = build_provider(provider, model)
        ok, reason = await inst.healthcheck()
    except ProviderError as exc:
        return ProviderInfo(name=provider.value, model="", available=False, reason=str(exc))
    return ProviderInfo(name=provider.value, model=inst.model, available=ok, reason=reason)


@router.get("", response_model=ConfigOut)
async def get_config(db: AsyncSession = Depends(get_db)) -> ConfigOut:
    settings = get_settings()
    active = await settings_store.get_runtime_provider(db)
    model = await settings_store.get_runtime_model(db, active)

    infos: list[ProviderInfo] = []
    for provider in FALLBACK_ORDER:
        infos.append(await _provider_info(db, provider))

    return ConfigOut(
        provider=active.value,
        model=model,
        providers=infos,
        fallback_enabled=settings.llm_fallback_enabled,
    )


@router.put("", response_model=ConfigOut)
async def update_config(
    body: ConfigUpdate, db: AsyncSession = Depends(get_db)
) -> ConfigOut:
    await settings_store.set_runtime_provider(db, body.provider)
    if body.model:
        await settings_store.set_runtime_model(db, body.provider, body.model)
    await db.commit()

    # Validate the newly selected provider is actually usable; surface a helpful
    # error otherwise (the client can still switch, but should know it's broken).
    info = await _provider_info(db, body.provider)
    if not info.available:
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{body.provider.value}' selected but unavailable: {info.reason}",
        )

    return await get_config(db)
