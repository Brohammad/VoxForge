"""Tests for invite email delivery."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from voxforge.config import Settings
from voxforge.infrastructure.email.invite_mailer import InviteEmailPayload, InviteEmailSender


@pytest.mark.asyncio
async def test_log_provider_does_not_deliver():
    sender = InviteEmailSender(Settings(email_provider="log"))
    sent = await sender.send_invite(
        InviteEmailPayload(
            to_email="user@example.com",
            org_name="Acme",
            accept_url="http://localhost/dashboard?invite=abc",
            role="member",
            expires_hours=72,
        )
    )
    assert sent is False
    assert sender.delivers_email is False


@pytest.mark.asyncio
async def test_resend_provider_sends_email():
    sender = InviteEmailSender(
        Settings(
            email_provider="resend",
            resend_api_key="re_test",
            email_from="VoxForge <noreply@example.com>",
        )
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"id":"email_123"}'

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "voxforge.infrastructure.email.invite_mailer.httpx.AsyncClient",
        return_value=mock_client,
    ):
        sent = await sender.send_invite(
            InviteEmailPayload(
                to_email="user@example.com",
                org_name="Acme",
                accept_url="https://app.example/dashboard?invite=abc",
                role="member",
                expires_hours=72,
            )
        )

    assert sent is True
    mock_client.post.assert_awaited_once()
    call_kwargs = mock_client.post.await_args.kwargs
    assert call_kwargs["json"]["to"] == ["user@example.com"]


@pytest.mark.asyncio
async def test_create_invite_api_hides_token_when_email_sent(auth_client, monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM", "VoxForge <noreply@example.com>")
    from voxforge.config import get_settings

    get_settings.cache_clear()

    register = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"owner-{uuid4().hex[:8]}@example.com",
            "password": "securepass123",
            "full_name": "Owner",
            "org_name": "Email Org",
        },
    )
    body = register.json()
    headers = {"Authorization": f"Bearer {body['tokens']['access_token']}"}
    org_id = body["org_id"]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"id":"email_123"}'
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "voxforge.infrastructure.email.invite_mailer.httpx.AsyncClient",
        return_value=mock_client,
    ):
        invite = await auth_client.post(
            f"/api/v1/orgs/{org_id}/invites",
            json={"email": f"invitee-{uuid4().hex[:8]}@example.com", "role": "member"},
            headers=headers,
        )

    assert invite.status_code == 201
    data = invite.json()
    assert data["email_sent"] is True
    assert data["token"] is None
    assert "accept_url" in data

    get_settings.cache_clear()
