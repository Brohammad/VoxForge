"""Integration tests for public demo endpoints."""

from uuid import UUID

import pytest

from voxforge.config import get_settings
from voxforge.infrastructure.db.models import (
    OrganizationMemberModel,
    OrganizationModel,
    UserModel,
)

DEMO_ORG_ID = UUID("a0000000-0000-4000-8000-000000000001")
DEMO_USER_ID = UUID("a0000000-0000-4000-8000-000000000002")


@pytest.fixture
async def demo_seeded(db_session):
    db_session.add(OrganizationModel(id=DEMO_ORG_ID, name="VoxForge Demo", slug="voxforge-demo"))
    db_session.add(
        UserModel(
            id=DEMO_USER_ID,
            email="demo@voxforge.io",
            hashed_password="hash",
            full_name="Demo User",
        )
    )
    db_session.add(OrganizationMemberModel(org_id=DEMO_ORG_ID, user_id=DEMO_USER_ID, role="owner"))
    await db_session.commit()


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.setenv("DEMO_ENABLED", "true")
    monkeypatch.setenv("DEMO_ORG_ID", str(DEMO_ORG_ID))
    monkeypatch.setenv("DEMO_USER_ID", str(DEMO_USER_ID))
    monkeypatch.setenv("STT_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_demo_info_when_enabled(test_client, demo_env, demo_seeded):
    res = await test_client.get("/api/v1/demo/info")
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "demo@voxforge.io"
    assert body["providers_mode"] in {"mock", "mixed", "live"}
    assert "stt_provider" in body


@pytest.mark.asyncio
async def test_demo_quickstart_runs_pipeline(test_client, demo_env, demo_seeded):
    res = await test_client.post("/api/v1/demo/quickstart")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "demo_turn_ok"
    assert body["session_id"]
    assert body["assistant_response"]
    assert body["e2e_ms"] is not None

    # Quickstart keeps the session open for follow-up /demo/chat turns.
    chat = await test_client.post(
        "/api/v1/demo/chat",
        json={"message": "Thanks, that helps.", "session_id": body["session_id"]},
    )
    assert chat.status_code == 200
    chat_body = chat.json()
    assert chat_body["session_id"] == body["session_id"]
    assert chat_body["assistant_response"]


@pytest.mark.asyncio
async def test_demo_disabled_returns_404(test_client, monkeypatch):
    monkeypatch.setenv("DEMO_ENABLED", "false")
    get_settings.cache_clear()
    res = await test_client.post("/api/v1/demo/quickstart")
    assert res.status_code == 404
    get_settings.cache_clear()
