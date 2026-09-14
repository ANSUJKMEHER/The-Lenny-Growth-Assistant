"""FastAPI application entrypoint.

Wires configuration, logging, CORS, database, API routers, static frontend, and
startup initialisation (table creation + best-effort sample ingestion).
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import artifacts, chat, config_api, health, ingest, sessions
from app.config import get_settings
from app.db import init_db, get_session_factory
from app.schemas import ErrorResponse

from pathlib import Path

# Resolve static asset directory relative to this file so the app works
# regardless of the current working directory (uvicorn, pytest, Docker).
_STATIC_DIR = Path(__file__).resolve().parent / "static"

# --------------------------------------------------------------------------- #
# Logging (structured, single-line key=value for easy grepping/log pipelines)
# --------------------------------------------------------------------------- #
_LOG_FORMAT = "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)
# Quiet noisy libraries.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    logger.info(
        "startup database_ready provider=%s model=%s",
        settings.llm_provider.value,
        settings.ollama_model,
    )

    # Best-effort corpus bootstrap: fetch the official Lenny's Podcast
    # transcripts on a fresh database (falling back to bundled samples when
    # offline) so a fresh clone has real grounding data to query.
    try:
        from app.core.rag import fetch

        async with get_session_factory()() as db:
            stats = await fetch.ensure_corpus(db)
            await db.commit()
            logger.info(
                "startup corpus sources_created=%d chunks_created=%d skipped=%d errors=%d",
                stats.sources_created,
                stats.chunks_created,
                stats.sources_skipped,
                len(stats.errors),
            )
    except Exception:  # pragma: no cover - bootstrap is non-fatal
        logger.exception("startup corpus bootstrap failed (continuing)")

    yield
    logger.info("shutdown")


settings = get_settings()
app = FastAPI(
    title="The Lenny Growth Assistant",
    version="0.1.0",
    description="Grounded AI assistant over Lenny's Podcast transcripts.",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# Structured error handler.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled error path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error="Internal server error", detail=str(exc)).model_dump(),
    )


# Routers
app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(config_api.router)
app.include_router(ingest.router)
app.include_router(artifacts.router)

# Static frontend + vendor assets.
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")
