"""API integration tests (SQLite backend; LLM intentionally unreachable)."""
import httpx
import pytest

from app.main import app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


async def test_readiness_reports_database_ok(client):
    res = await client.get("/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["checks"]["database"]["status"] == "ok"


async def test_conversation_lifecycle(client):
    # Create
    res = await client.post("/api/sessions", json={"title": "My session"})
    assert res.status_code == 201
    conv = res.json()
    assert conv["title"] == "My session"
    assert conv["id"]

    # List
    res = await client.get("/api/sessions")
    assert res.status_code == 200
    assert len(res.json()["sessions"]) == 1

    # Get
    res = await client.get(f"/api/sessions/{conv['id']}")
    assert res.status_code == 200
    assert res.json()["messages"] == []

    # Delete
    res = await client.delete(f"/api/sessions/{conv['id']}")
    assert res.status_code == 204

    res = await client.get("/api/sessions")
    assert len(res.json()["sessions"]) == 0


async def test_get_missing_conversation_404(client):
    res = await client.get("/api/sessions/doesnotexist")
    assert res.status_code == 404


async def test_message_validation(client):
    res = await client.post(
        "/api/sessions", json={"title": "validation"}
    )
    conv_id = res.json()["id"]
    res = await client.post(f"/api/sessions/{conv_id}/messages", json={"content": ""})
    assert res.status_code == 422


async def test_message_with_no_provider_returns_503(client):
    """Graceful failure when no LLM backend is reachable."""
    res = await client.post("/api/sessions", json={"title": "t"})
    conv_id = res.json()["id"]
    res = await client.post(
        f"/api/sessions/{conv_id}/messages", json={"content": "hello"}
    )
    assert res.status_code == 503
    assert "LLM" in res.json()["detail"] or "provider" in res.json()["detail"].lower()


async def test_config_endpoint(client):
    res = await client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    assert body["provider"] == "ollama"
    assert any(p["name"] == "ollama" for p in body["providers"])


async def test_stream_endpoint_validates(client):
    res = await client.post("/api/sessions", json={"title": "s"})
    conv_id = res.json()["id"]
    res = await client.post(f"/api/sessions/{conv_id}/messages/stream", json={"content": ""})
    assert res.status_code == 422


async def test_stream_endpoint_no_provider_503(client):
    res = await client.post("/api/sessions", json={"title": "s"})
    conv_id = res.json()["id"]
    res = await client.post(f"/api/sessions/{conv_id}/messages/stream", json={"content": "hello"})
    assert res.status_code == 503
