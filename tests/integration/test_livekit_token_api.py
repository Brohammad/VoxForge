"""Integration tests for LiveKit token HTTP API (no WebRTC room required)."""

from uuid import uuid4

import pytest

from voxforge.config import get_settings


@pytest.mark.asyncio
async def test_livekit_token_endpoint_returns_503_when_disabled(auth_client, monkeypatch):
    for key in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()

    register = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"lk-off-{uuid4().hex[:8]}@example.com",
            "password": "securepass123",
            "full_name": "LK User",
            "org_name": "LK Org",
        },
    )
    token = register.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    session = await auth_client.post(
        "/api/v1/sessions",
        json={"transport_type": "webrtc"},
        headers=headers,
    )
    assert session.status_code == 201
    session_id = session.json()["session_id"]

    response = await auth_client.post(
        f"/api/v1/livekit/sessions/{session_id}/token",
        json={"participant_identity": "user-1"},
        headers=headers,
    )
    assert response.status_code == 503
    assert "livekit" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_livekit_token_endpoint_returns_404_for_unknown_session(auth_client, monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-at-least-32-characters-long")
    get_settings.cache_clear()

    register = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"lk-404-{uuid4().hex[:8]}@example.com",
            "password": "securepass123",
            "full_name": "LK User",
            "org_name": "LK Org",
        },
    )
    token = register.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    missing_id = "00000000-0000-0000-0000-000000009999"
    response = await auth_client.post(
        f"/api/v1/livekit/sessions/{missing_id}/token",
        json={"participant_identity": "user-1"},
        headers=headers,
    )
    assert response.status_code == 404
