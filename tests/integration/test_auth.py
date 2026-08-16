import pytest


@pytest.mark.asyncio
async def test_register_and_login(auth_client):
    register_resp = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "securepass123",
            "full_name": "Alice",
            "org_name": "Acme Corp",
        },
    )
    assert register_resp.status_code == 201
    data = register_resp.json()
    assert data["email"] == "alice@example.com"
    assert "tokens" in data
    assert data["tokens"]["access_token"]

    login_resp = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "securepass123"},
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["access_token"]


@pytest.mark.asyncio
async def test_me_endpoint(auth_client):
    register_resp = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "bob@example.com",
            "password": "securepass123",
            "full_name": "Bob",
            "org_name": "Bob Inc",
        },
    )
    token = register_resp.json()["tokens"]["access_token"]

    me_resp = await auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["email"] == "bob@example.com"


@pytest.mark.asyncio
async def test_sessions_require_auth(auth_client):
    response = await auth_client.post("/api/v1/sessions", json={})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_session_crud(auth_client):
    register_resp = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "carol@example.com",
            "password": "securepass123",
            "full_name": "Carol",
            "org_name": "Carol LLC",
        },
    )
    token = register_resp.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await auth_client.post("/api/v1/sessions", json={}, headers=headers)
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    get_resp = await auth_client.get(f"/api/v1/sessions/{session_id}", headers=headers)
    assert get_resp.status_code == 200

    delete_resp = await auth_client.delete(f"/api/v1/sessions/{session_id}", headers=headers)
    assert delete_resp.status_code == 200


@pytest.mark.asyncio
async def test_api_key_auth(auth_client):
    register_resp = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": "dave@example.com",
            "password": "securepass123",
            "full_name": "Dave",
            "org_name": "Dave Co",
        },
    )
    token = register_resp.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    key_resp = await auth_client.post(
        "/api/v1/api-keys",
        json={"name": "test-key"},
        headers=headers,
    )
    assert key_resp.status_code == 201
    raw_key = key_resp.json()["raw_key"]

    session_resp = await auth_client.post(
        "/api/v1/sessions",
        json={},
        headers={"X-API-Key": raw_key},
    )
    assert session_resp.status_code == 201


@pytest.mark.asyncio
async def test_duplicate_registration(auth_client):
    payload = {
        "email": "eve@example.com",
        "password": "securepass123",
        "full_name": "Eve",
        "org_name": "Eve Org",
    }
    assert (await auth_client.post("/api/v1/auth/register", json=payload)).status_code == 201
    dup = await auth_client.post("/api/v1/auth/register", json=payload)
    assert dup.status_code == 400


@pytest.mark.asyncio
async def test_registration_disabled_returns_403(auth_client, monkeypatch):
    from voxforge.config import get_settings

    monkeypatch.setenv("REGISTRATION_ENABLED", "false")
    get_settings.cache_clear()
    try:
        resp = await auth_client.post(
            "/api/v1/auth/register",
            json={
                "email": "locked-out@example.com",
                "password": "securepass123",
                "full_name": "Locked Out",
                "org_name": "Locked Org",
            },
        )
        assert resp.status_code == 403
        assert "registration is disabled" in resp.json()["detail"].lower()
    finally:
        get_settings.cache_clear()
