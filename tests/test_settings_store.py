"""Runtime settings store: provider/model toggle persistence (upsert)."""
from app.config import Provider
from app.core import settings_store


async def test_set_runtime_provider_is_idempotent(db):
    """Switching the provider more than once must not raise a unique-constraint
    violation (regression: ``app_settings`` used ``db.add`` which duplicated the
    primary key on the second write)."""
    await settings_store.set_runtime_provider(db, Provider.ANTHROPIC)
    await db.commit()

    await settings_store.set_runtime_provider(db, Provider.OPENAI)
    await db.commit()

    assert await settings_store.get_runtime_provider(db) == Provider.OPENAI


async def test_set_runtime_model_is_idempotent(db):
    """Setting a model override repeatedly updates the existing row in place."""
    await settings_store.set_runtime_model(db, Provider.OLLAMA, "llama3.1")
    await db.commit()

    await settings_store.set_runtime_model(db, Provider.OLLAMA, "llama3.2")
    await db.commit()

    assert await settings_store.get_runtime_model(db, Provider.OLLAMA) == "llama3.2"


async def test_runtime_defaults_when_no_override(db):
    """With no override, the env-provided defaults are returned."""
    assert await settings_store.get_runtime_provider(db) == Provider.OLLAMA
    assert await settings_store.get_runtime_model(db, Provider.OLLAMA) == "qwen2.5:7b"
