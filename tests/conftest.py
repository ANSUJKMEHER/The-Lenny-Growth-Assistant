"""Shared pytest fixtures.

The test suite runs against SQLite (via aiosqlite) so no PostgreSQL or Ollama is
required, and the LLM layer is exercised with a deterministic fake provider. The
real embedding path degrades to the lexical fallback when Ollama is absent, which
is exactly what these tests cover.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# --- Ensure `app` is importable from the backend directory ------------------ #
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

# --- Point configuration at SQLite BEFORE the app modules are imported ------ #
_DB_FILE = Path(tempfile.gettempdir()) / "lenny_test.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_FILE}"
os.environ["AUTO_CREATE_TABLES"] = "true"
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"  # guaranteed-unreachable
os.environ["LLM_FALLBACK_ENABLED"] = "false"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

import app.db as dbmod  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, get_engine, get_session_factory, init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _configure() -> None:
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._session_factory = None


@pytest_asyncio.fixture(autouse=True)
async def clean_db(_configure) -> None:
    """Recreate the schema and truncate tables before every test."""
    dbmod._engine = None
    dbmod._session_factory = None
    await init_db()
    async with get_engine().begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    yield


@pytest_asyncio.fixture
async def db():
    factory = get_session_factory()
    async with factory() as session:
        yield session
