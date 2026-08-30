"""Tests for the Zendesk ticketing adapter."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from voxforge.config import Settings
from voxforge.core.domain.support import TicketCreateRequest
from voxforge.core.exceptions import ProviderError
from voxforge.infrastructure.providers.support.factory import create_ticketing_provider
from voxforge.infrastructure.providers.support.mock import MockTicketingProvider
from voxforge.infrastructure.providers.support.zendesk import (
    ZendeskTicketingProvider,
)


def _ticket(**overrides):
    data = {
        "id": 42,
        "subject": "Refund request",
        "description": "Customer requested a refund",
        "status": "solved",
        "priority": "high",
        "requester": {"email": "customer@example.com"},
        "created_at": "2026-08-30T06:00:00Z",
        "updated_at": "2026-08-30T06:05:00Z",
    }
    data.update(overrides)
    return data


def _provider(handler) -> ZendeskTicketingProvider:
    return ZendeskTicketingProvider(
        subdomain="acme",
        email="agent@example.com",
        api_token="secret-token",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_create_ticket_maps_handoff_context_and_auth():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v2/search.json":
            return httpx.Response(200, json={"results": []})
        assert request.url.path == "/api/v2/tickets.json"
        payload = json.loads(request.content)
        body = payload["ticket"]["comment"]["body"]
        assert "Customer cannot reset password" in body
        assert "Conversation summary:" in body
        assert "VoxForge replay: https://voice.example/replay/abc" in body
        assert "voxforge_session_session_123" in payload["ticket"]["tags"]
        assert payload["ticket"]["requester"]["email"] == "customer@example.com"
        return httpx.Response(201, json={"ticket": _ticket(status="new")})

    ticket = await _provider(handler).create_ticket(
        TicketCreateRequest(
            subject="Password reset",
            description="Customer cannot reset password",
            customer_email="customer@example.com",
            priority="urgent",
            session_id="session-123",
            conversation_summary="Password reset link expired.",
            replay_url="https://voice.example/replay/abc",
        )
    )

    assert ticket.id == "42"
    assert ticket.status == "open"
    expected = base64.b64encode(b"agent@example.com/token:secret-token").decode()
    assert requests[-1].headers["authorization"] == f"Basic {expected}"


@pytest.mark.asyncio
async def test_create_ticket_returns_existing_session_ticket():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json={"results": [_ticket(id=99)]})

    ticket = await _provider(handler).create_ticket(
        TicketCreateRequest(
            subject="Duplicate",
            description="Should not create",
            session_id="same-session",
        )
    )

    assert ticket.id == "99"
    assert calls == ["GET"]


@pytest.mark.asyncio
async def test_lookup_ticket_and_customer_email():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/tickets/404.json":
            return httpx.Response(404)
        if request.url.path == "/api/v2/tickets/42.json":
            return httpx.Response(200, json={"ticket": _ticket()})
        assert request.url.params["query"] == 'type:ticket requester:"customer@example.com"'
        return httpx.Response(200, json={"results": [_ticket(), _ticket(id=43)]})

    provider = _provider(handler)
    assert await provider.lookup_ticket("../search") is None
    assert await provider.lookup_ticket("404") is None
    ticket = await provider.lookup_ticket("42")
    assert ticket is not None
    assert ticket.status == "resolved"
    tickets = await provider.lookup_by_customer_email("customer@example.com", limit=1)
    assert [ticket.id for ticket in tickets] == ["42"]


@pytest.mark.asyncio
async def test_zendesk_http_error_is_sanitized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            headers={"x-request-id": "req-123"},
            json={"error": "token secret must not escape"},
        )

    with pytest.raises(ProviderError, match=r"HTTP 401 \(request_id=req-123\)"):
        await _provider(handler).lookup_ticket("42")


def test_zendesk_rejects_invalid_configuration():
    with pytest.raises(ProviderError, match="subdomain"):
        ZendeskTicketingProvider(
            subdomain="https://evil.example",
            email="agent@example.com",
            api_token="token",
        )


def test_ticketing_factory_supports_mock_and_zendesk():
    mock_provider = create_ticketing_provider(Settings(ticketing_provider="mock"))
    assert isinstance(mock_provider, MockTicketingProvider)

    provider = create_ticketing_provider(
        Settings(
            ticketing_provider="zendesk",
            zendesk_subdomain="acme",
            zendesk_email="agent@example.com",
            zendesk_api_token="token",
        )
    )
    assert isinstance(provider, ZendeskTicketingProvider)


def test_ticketing_factory_keeps_freshdesk_blocked():
    with pytest.raises(ProviderError, match="unimplemented stub"):
        create_ticketing_provider(Settings(ticketing_provider="freshdesk"))
