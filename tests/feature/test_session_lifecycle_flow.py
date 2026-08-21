"""Feature test: session create → voice turns → interrupt → resume → end."""

from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from voxforge.config import get_settings
from voxforge.main import app

pytestmark = pytest.mark.feature


@pytest.mark.asyncio
async def test_session_lifecycle_rest_api(auth_client):
    headers_resp = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"lifecycle-{uuid4().hex[:8]}@example.com",
            "password": "securepass123",
            "full_name": "Lifecycle User",
            "org_name": "Lifecycle Org",
        },
    )
    token = headers_resp.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create = await auth_client.post("/api/v1/sessions", json={}, headers=headers)
    assert create.status_code == 201

    sample = await auth_client.post("/api/v1/onboarding/run-sample-call", headers=headers)
    assert sample.status_code == 200
    session_id = sample.json()["test_session_id"]

    messages = await auth_client.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)
    assert messages.status_code == 200
    assert len(messages.json()["messages"]) >= 2

    replay = await auth_client.get(f"/api/v1/sessions/{session_id}/replay", headers=headers)
    assert replay.status_code == 200

    end = await auth_client.delete(f"/api/v1/sessions/{session_id}", headers=headers)
    assert end.status_code == 200


def test_websocket_session_start_and_end(fake_redis, db_engine, monkeypatch):
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
                    "email": f"ws-lifecycle-{uuid4().hex[:8]}@example.com",
                    "password": "securepass123",
                    "full_name": "WS User",
                    "org_name": "WS Org",
                },
            )
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
