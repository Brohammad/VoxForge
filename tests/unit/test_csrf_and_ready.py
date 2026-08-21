"""CSRF and readiness behavior tests."""

from uuid import uuid4

import pytest

from voxforge.config import Settings
from voxforge.infrastructure.observability.health import _aggregate_status


def test_aggregate_status_degraded_defaults_to_200():
    status, code = _aggregate_status({"database": "ok", "redis": "ok", "mcp_registry": "degraded"})
    assert status == "degraded"
    assert code == 200


def test_aggregate_status_degraded_can_fail_closed():
    status, code = _aggregate_status(
        {"database": "ok", "redis": "ok", "mcp_registry": "degraded"},
        fail_on_degraded=True,
    )
    assert status == "degraded"
    assert code == 503


def test_aggregate_status_critical_unavailable():
    status, code = _aggregate_status({"database": "error: down", "redis": "ok"})
    assert status == "unavailable"
    assert code == 503


@pytest.mark.asyncio
async def test_cookie_mutating_request_requires_csrf(auth_client):
    email = f"csrf-{uuid4().hex[:8]}@example.com"
    register = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "securepass123",
            "full_name": "CSRF User",
            "org_name": "CSRF Org",
        },
    )
    assert register.status_code == 201
    # Cookie session present; no Bearer — mutating call must include CSRF.
    auth_client.cookies.clear()
    # Re-login to get cookies without storing Bearer in headers for next call
    login = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    assert login.status_code == 200
    assert "voxforge_access" in login.cookies
    assert "voxforge_csrf" in login.cookies

    blocked = await auth_client.post("/api/v1/sessions", json={})
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "csrf_failed"

    csrf = login.cookies["voxforge_csrf"]
    allowed = await auth_client.post(
        "/api/v1/sessions",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert allowed.status_code == 201


def test_settings_ready_fail_on_degraded_default():
    assert Settings().ready_fail_on_degraded is False
