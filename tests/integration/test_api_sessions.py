from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_create_session_via_api(test_client):
    response = await test_client.post(
        "/api/v1/sessions",
        json={"transport_type": "websocket", "config": {"language": "en"}},
    )
    assert response.status_code == 201
    data = response.json()
    assert "session_id" in data
    assert data["ws_url"] == "/api/v1/ws/voice"
    assert data["status"] == "created"


@pytest.mark.asyncio
async def test_create_session_rejects_unknown_config_keys(test_client):
    response = await test_client.post(
        "/api/v1/sessions",
        json={"transport_type": "websocket", "config": {"language": "en", "evil": True}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_session_via_api(test_client):
    create_resp = await test_client.post("/api/v1/sessions", json={})
    session_id = create_resp.json()["session_id"]

    response = await test_client.get(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == session_id
    assert data["status"] == "created"


@pytest.mark.asyncio
async def test_get_session_not_found(test_client):
    response = await test_client.get(f"/api/v1/sessions/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_end_session_via_api(test_client):
    create_resp = await test_client.post("/api/v1/sessions", json={})
    session_id = create_resp.json()["session_id"]

    response = await test_client.delete(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_get_messages_empty(test_client):
    create_resp = await test_client.post("/api/v1/sessions", json={})
    session_id = create_resp.json()["session_id"]

    response = await test_client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == []
