"""Zendesk ticketing adapter."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from voxforge.core.domain.support import SupportTicket, TicketCreateRequest
from voxforge.core.exceptions import ProviderError
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.observability.provider_errors import record_provider_error

logger = get_logger(__name__)

_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_STATUS_MAP = {
    "new": "open",
    "open": "open",
    "pending": "pending",
    "hold": "pending",
    "solved": "resolved",
    "closed": "closed",
}
_PRIORITIES = frozenset({"low", "normal", "high", "urgent"})


class ZendeskTicketingProvider:
    """Create and retrieve Zendesk tickets using API-token authentication."""

    def __init__(
        self,
        *,
        subdomain: str,
        email: str,
        api_token: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        normalized_subdomain = subdomain.strip().lower()
        if not _SUBDOMAIN_RE.fullmatch(normalized_subdomain):
            raise ProviderError("zendesk", "Invalid or missing Zendesk subdomain")
        if not email.strip():
            raise ProviderError("zendesk", "Zendesk account email is required")
        if not api_token.strip():
            raise ProviderError("zendesk", "Zendesk API token is required")

        self._base_url = f"https://{normalized_subdomain}.zendesk.com/api/v2"
        self._auth = httpx.BasicAuth(f"{email.strip()}/token", api_token.strip())
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def lookup_ticket(self, ticket_id: str) -> SupportTicket | None:
        if not ticket_id.strip().isdigit():
            return None
        response = await self._request("GET", f"/tickets/{ticket_id}.json", "lookup_ticket")
        if response.status_code == 404:
            return None
        self._raise_for_status(response, "lookup_ticket")
        return _to_support_ticket(response.json()["ticket"])

    async def lookup_by_customer_email(
        self,
        email: str,
        *,
        limit: int = 5,
    ) -> list[SupportTicket]:
        response = await self._request(
            "GET",
            "/search.json",
            "lookup_by_customer_email",
            params={
                "query": f'type:ticket requester:"{_escape_search_value(email)}"',
                "per_page": max(1, min(limit, 100)),
                "sort_by": "created_at",
                "sort_order": "desc",
            },
        )
        self._raise_for_status(response, "lookup_by_customer_email")
        return [_to_support_ticket(ticket) for ticket in response.json().get("results", [])[:limit]]

    async def create_ticket(self, request: TicketCreateRequest) -> SupportTicket:
        session_tag = _session_tag(request.session_id)
        if session_tag:
            existing = await self._lookup_by_tag(session_tag)
            if existing is not None:
                return existing

        tags = ["voxforge"]
        if session_tag:
            tags.append(session_tag)

        ticket: dict[str, Any] = {
            "subject": request.subject,
            "comment": {"body": _ticket_body(request), "public": False},
            "priority": request.priority if request.priority in _PRIORITIES else "normal",
            "tags": tags,
        }
        if request.customer_email:
            ticket["requester"] = {"email": request.customer_email}

        response = await self._request(
            "POST",
            "/tickets.json",
            "create_ticket",
            json={"ticket": ticket},
        )
        self._raise_for_status(response, "create_ticket")
        return _to_support_ticket(response.json()["ticket"])

    async def _lookup_by_tag(self, tag: str) -> SupportTicket | None:
        response = await self._request(
            "GET",
            "/search.json",
            "lookup_by_session",
            params={"query": f"type:ticket tags:{tag}", "per_page": 1},
        )
        self._raise_for_status(response, "lookup_by_session")
        results = response.json().get("results", [])
        return _to_support_ticket(results[0]) if results else None

    async def _request(
        self,
        method: str,
        path: str,
        operation: str,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                auth=self._auth,
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                return await client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            record_provider_error("zendesk", operation)
            logger.error("zendesk_ticketing_error", operation=operation, error=str(exc))
            raise ProviderError("zendesk", f"{operation} request failed") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        if response.is_success:
            return
        record_provider_error("zendesk", operation)
        request_id = response.headers.get("x-request-id")
        suffix = f" (request_id={request_id})" if request_id else ""
        raise ProviderError(
            "zendesk",
            f"{operation} returned HTTP {response.status_code}{suffix}",
        )


def _session_tag(session_id: str | None) -> str | None:
    if not session_id:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", session_id.lower()).strip("_")
    return f"voxforge_session_{normalized}"[:255]


def _escape_search_value(value: str) -> str:
    return value.strip().replace("\\", "\\\\").replace('"', '\\"')


def _ticket_body(request: TicketCreateRequest) -> str:
    sections = [request.description]
    if request.conversation_summary:
        sections.extend(["", "Conversation summary:", request.conversation_summary])
    if request.replay_url:
        sections.extend(["", f"VoxForge replay: {request.replay_url}"])
    if request.session_id:
        sections.extend(["", f"VoxForge session: {request.session_id}"])
    return "\n".join(sections)


def _to_support_ticket(data: dict[str, Any]) -> SupportTicket:
    requester = data.get("requester") or {}
    return SupportTicket(
        id=str(data["id"]),
        subject=data.get("subject") or "(no subject)",
        description=data.get("description") or data.get("raw_subject") or "",
        status=_STATUS_MAP.get(str(data.get("status", "")).lower(), "open"),
        priority=(data["priority"] if data.get("priority") in _PRIORITIES else "normal"),
        customer_email=requester.get("email"),
        created_at=_parse_datetime(data.get("created_at")),
        updated_at=_parse_datetime(data.get("updated_at")) if data.get("updated_at") else None,
    )


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
