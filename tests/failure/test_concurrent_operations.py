"""Failure-mode tests: concurrent operations and duplicate requests."""

import asyncio
from uuid import uuid4

import pytest

pytestmark = pytest.mark.failure


@pytest.mark.asyncio
async def test_concurrent_session_creation(auth_client):
    register = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"concurrent-{uuid4().hex[:8]}@example.com",
            "password": "securepass123",
            "full_name": "Concurrent User",
            "org_name": "Concurrent Org",
        },
    )
    token = register.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    async def create_session():
        return await auth_client.post("/api/v1/sessions", json={}, headers=headers)

    results = await asyncio.gather(*[create_session() for _ in range(10)])
    assert all(r.status_code == 201 for r in results)
    session_ids = {r.json()["session_id"] for r in results}
    assert len(session_ids) == 10


@pytest.mark.asyncio
async def test_concurrent_handoff_idempotent(auth_client, monkeypatch):
    monkeypatch.setenv("HANDOFF_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    from voxforge.config import get_settings

    get_settings.cache_clear()

    register = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"handoff-race-{uuid4().hex[:8]}@example.com",
            "password": "securepass123",
            "full_name": "Handoff Race",
            "org_name": "Handoff Race Org",
        },
    )
    token = register.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    session = await auth_client.post("/api/v1/sessions", json={}, headers=headers)
    session_id = session.json()["session_id"]

    async def initiate():
        return await auth_client.post(
            f"/api/v1/sessions/{session_id}/handoff",
            json={"trigger": "user_request", "reason": "concurrent"},
            headers=headers,
        )

    results = await asyncio.gather(*[initiate() for _ in range(5)])
    assert all(r.status_code == 201 for r in results)
    handoff_ids = {r.json()["id"] for r in results}
    assert len(handoff_ids) == 1
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_repeated_replay_token_verification():
    from uuid import uuid4

    from voxforge.config import Settings
    from voxforge.modules.handoff.application.replay_link import ReplayLinkService

    settings = Settings(
        jwt_secret_key="test-secret-key-at-least-32-bytes-long",
        public_base_url="http://localhost:8000",
    )
    service = ReplayLinkService(settings)
    session_id = uuid4()
    org_id = uuid4()
    handoff_id = uuid4()
    _, token = service.generate(session_id=session_id, org_id=org_id, handoff_id=handoff_id)

    assert service.verify(session_id=session_id, org_id=org_id, handoff_id=handoff_id, token=token)
    assert service.verify(session_id=session_id, org_id=org_id, handoff_id=handoff_id, token=token)
    assert not service.verify(
        session_id=session_id, org_id=org_id, handoff_id=handoff_id, token="tampered.sig"
    )
