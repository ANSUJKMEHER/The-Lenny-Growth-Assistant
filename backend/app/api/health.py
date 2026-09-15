"""Health and readiness endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings_store
from app.core.llm.factory import build_provider
from app.core.llm.base import ProviderError
from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness: the process is up."""
    return {"status": "ok", "service": "lenny-growth-assistant"}


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Readiness: the database and the *active* LLM provider are reachable.

    Returns HTTP 200 when ready and 503 when not, so orchestrators and the
    Docker healthcheck can gate on it conventionally.
    """
    checks: dict[str, dict] = {}

    # Database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}

    # LLM provider — report the runtime-active provider (persisted via
    # /api/config), not the env default, so readiness matches what chat uses.
    active = await settings_store.get_runtime_provider(db)
    model = await settings_store.get_runtime_model(db, active)
    try:
        provider = build_provider(active, model)
        ok, reason = await provider.healthcheck()
        checks["llm"] = {
            "provider": provider.name,
            "model": provider.model,
            "status": "ok" if ok else "degraded",
            "detail": reason,
        }
    except ProviderError as exc:
        checks["llm"] = {
            "provider": active.value,
            "model": model,
            "status": "error",
            "detail": str(exc),
        }

    overall = all(c.get("status") in ("ok", "degraded") for c in checks.values())
    status = "ready" if overall else "not_ready"
    return JSONResponse(
        status_code=200 if overall else 503,
        content={"status": status, "checks": checks},
    )
