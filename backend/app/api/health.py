"""Health and readiness endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.llm.factory import build_provider
from app.core.llm.base import ProviderError
from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness: the process is up."""
    return {"status": "ok", "service": "lenny-growth-assistant"}


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness: database, provider, and (optionally) Ollama are reachable."""
    checks: dict[str, dict] = {}

    # Database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}

    # LLM provider
    settings = get_settings()
    try:
        provider = build_provider(settings.llm_provider)
        ok, reason = await provider.healthcheck()
        checks["llm"] = {
            "provider": provider.name,
            "model": provider.model,
            "status": "ok" if ok else "degraded",
            "detail": reason,
        }
    except ProviderError as exc:
        checks["llm"] = {
            "provider": settings.llm_provider.value,
            "status": "error",
            "detail": str(exc),
        }

    overall = all(
        c.get("status") in ("ok", "degraded") for c in checks.values()
    )
    return {"status": "ready" if overall else "not_ready", "checks": checks}
