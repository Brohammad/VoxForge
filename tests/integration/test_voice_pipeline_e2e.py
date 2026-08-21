from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from voxforge.config import get_settings
from voxforge.main import app


async def _register_token(auth_client, email: str) -> str:
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "securepass123",
            "full_name": "Voice E2E User",
            "org_name": "Voice E2E Org",
        },
    )
    assert response.status_code == 201
    return response.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_programmatic_pipeline_persists_turn_artifacts(auth_client):
    """E2E: onboarding sample call writes messages, metrics, evaluations, outcomes."""
    token = await _register_token(auth_client, f"pipeline-e2e-{uuid4().hex[:8]}@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = await auth_client.post("/api/v1/onboarding/run-sample-call", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "test_call_passed"
    session_id = response.json()["test_session_id"]

    messages = await auth_client.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)
    assert messages.status_code == 200
    assert len(messages.json()["messages"]) >= 2

    evaluations = await auth_client.get(
        f"/api/v1/sessions/{session_id}/evaluations",
        headers=headers,
    )
    assert evaluations.status_code == 200
    assert len(evaluations.json()["evaluations"]) >= 1

    outcomes = await auth_client.get("/api/v1/dashboard/outcomes", headers=headers)
    assert outcomes.status_code == 200
    assert outcomes.json()["total_sessions"] >= 1


def test_websocket_voice_session_lifecycle(fake_redis, db_engine, monkeypatch):
    """E2E: WebSocket gateway starts and ends a session with mock providers configured."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from voxforge.infrastructure import db as db_module
    from voxforge.infrastructure import redis as redis_module

    async def _noop_init(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("voxforge.main.init_db", _noop_init)
    monkeypatch.setattr("voxforge.main.init_redis", _noop_init)
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-at-least-32-bytes-long")
    monkeypatch.setenv("API_KEY_HASH_PEPPER", "test-pepper")
    get_settings.cache_clear()

    db_module.session._engine = db_engine
    db_module.session._session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    redis_module.client._redis = fake_redis

    try:
        with TestClient(app) as client:
            register = client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"ws-e2e-{uuid4().hex[:8]}@example.com",
                    "password": "securepass123",
                    "full_name": "Voice E2E User",
                    "org_name": "Voice E2E Org",
                },
            )
            assert register.status_code == 201
            token = register.json()["tokens"]["access_token"]

            with client.websocket_connect("/api/v1/ws/voice") as ws:
                ws.send_json(
                    {
                        "type": "start",
                        "token": token,
                        "config": {"language": "en"},
                    }
                )
                started = ws.receive_json()
                assert started["type"] == "started"
                session_id = started["session_id"]

                ws.send_json({"type": "end"})
                ended = ws.receive_json()
                assert ended["type"] == "ended"
                assert ended["session_id"] == session_id
    finally:
        db_module.session._engine = None
        db_module.session._session_factory = None
        redis_module.client._redis = None
        get_settings.cache_clear()
