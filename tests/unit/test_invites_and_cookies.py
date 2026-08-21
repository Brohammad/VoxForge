"""Tests for org invites and auth cookies."""

from hashlib import sha256
from uuid import uuid4

import pytest

from voxforge.config import Settings, get_settings
from voxforge.core.domain.auth import OrgRole, Principal, PrincipalType, RegisterRequest, TokenPair
from voxforge.infrastructure.security.cookies import clear_auth_cookies, set_auth_cookies
from voxforge.modules.auth.application.service import AuthService


@pytest.mark.asyncio
async def test_create_and_accept_invite(db_session):
    settings = get_settings()
    auth = AuthService(db_session, settings)
    owner, org, _tokens = await auth.register(
        RegisterRequest(
            email=f"owner-{uuid4().hex[:8]}@example.com",
            password="securepass123",
            full_name="Owner",
            org_name="Invite Org",
        )
    )
    await auth.commit()

    actor = Principal(
        type=PrincipalType.USER,
        user_id=owner.id,
        org_id=org.id,
        role=OrgRole.OWNER,
    )
    invite, raw_token, accept_url = await auth.create_invite(
        org_id=org.id,
        email=f"member-{uuid4().hex[:8]}@example.com",
        role=OrgRole.MEMBER,
        actor=actor,
    )
    await auth.commit()
    assert invite.id is not None
    assert raw_token in accept_url
    assert sha256(raw_token.encode()).hexdigest() == invite.token_hash

    user, org_id, tokens = await auth.accept_invite(
        token=raw_token,
        password="securepass123",
        full_name="New Member",
    )
    await auth.commit()
    assert org_id == org.id
    assert user.email == invite.email
    assert tokens.access_token


@pytest.mark.asyncio
async def test_login_sets_httponly_cookie(auth_client):
    email = f"cookie-{uuid4().hex[:8]}@example.com"
    await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "securepass123",
            "full_name": "Cookie User",
            "org_name": "Cookie Org",
        },
    )
    response = await auth_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    assert response.status_code == 200
    assert "voxforge_access" in response.cookies

    me = await auth_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email


def test_cookie_helpers_respect_disabled_flag():
    from starlette.responses import Response

    settings = Settings(auth_cookies_enabled=False)
    response = Response()
    set_auth_cookies(
        response,
        TokenPair(access_token="a", refresh_token="r", token_type="bearer", expires_in=3600),
        settings,
    )
    assert "set-cookie" not in {k.lower() for k in response.headers.keys()}
    clear_auth_cookies(response, settings)
