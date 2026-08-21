"""Org invite email delivery (log, Resend, SMTP)."""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from voxforge.config import Settings
from voxforge.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class InviteEmailPayload:
    to_email: str
    org_name: str
    accept_url: str
    role: str
    expires_hours: int


class InviteEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def delivers_email(self) -> bool:
        return self._settings.email_provider.lower() in {"resend", "smtp"}

    async def send_invite(self, payload: InviteEmailPayload) -> bool:
        provider = self._settings.email_provider.lower()
        if provider == "resend":
            return await self._send_resend(payload)
        if provider == "smtp":
            return await self._send_smtp(payload)
        logger.info(
            "invite_email_log_only",
            to=payload.to_email,
            org=payload.org_name,
            accept_url=payload.accept_url,
            role=payload.role,
        )
        return False

    def _subject(self, org_name: str) -> str:
        return f"You're invited to {org_name} on VoxForge"

    def _body_text(self, payload: InviteEmailPayload) -> str:
        return (
            f"You've been invited to join {payload.org_name} on VoxForge as {payload.role}.\n\n"
            f"Accept your invite (expires in {payload.expires_hours} hours):\n"
            f"{payload.accept_url}\n"
        )

    def _body_html(self, payload: InviteEmailPayload) -> str:
        return (
            f"<p>You've been invited to join <strong>{payload.org_name}</strong> "
            f"on VoxForge as <strong>{payload.role}</strong>.</p>"
            f'<p><a href="{payload.accept_url}">Accept invite</a> '
            f"(expires in {payload.expires_hours} hours)</p>"
        )

    async def _send_resend(self, payload: InviteEmailPayload) -> bool:
        api_key = self._settings.resend_api_key.strip()
        if not api_key:
            logger.warning("invite_email_resend_missing_api_key", to=payload.to_email)
            return False

        body = {
            "from": self._settings.email_from,
            "to": [payload.to_email],
            "subject": self._subject(payload.org_name),
            "text": self._body_text(payload),
            "html": self._body_html(payload),
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            if response.status_code >= 400:
                logger.warning(
                    "invite_email_resend_failed",
                    to=payload.to_email,
                    status=response.status_code,
                    detail=response.text[:500],
                )
                return False
            logger.info("invite_email_sent", provider="resend", to=payload.to_email)
            return True
        except Exception as exc:
            logger.warning(
                "invite_email_resend_error",
                to=payload.to_email,
                error=str(exc),
            )
            return False

    async def _send_smtp(self, payload: InviteEmailPayload) -> bool:
        host = self._settings.smtp_host.strip()
        if not host:
            logger.warning("invite_email_smtp_missing_host", to=payload.to_email)
            return False

        message = EmailMessage()
        message["From"] = self._settings.email_from
        message["To"] = payload.to_email
        message["Subject"] = self._subject(payload.org_name)
        message.set_content(self._body_text(payload))
        message.add_alternative(self._body_html(payload), subtype="html")

        def _deliver() -> None:
            if self._settings.smtp_use_tls:
                with smtplib.SMTP(host, self._settings.smtp_port, timeout=15) as smtp:
                    smtp.starttls()
                    if self._settings.smtp_user:
                        smtp.login(self._settings.smtp_user, self._settings.smtp_password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(host, self._settings.smtp_port, timeout=15) as smtp:
                    if self._settings.smtp_user:
                        smtp.login(self._settings.smtp_user, self._settings.smtp_password)
                    smtp.send_message(message)

        try:
            await asyncio.to_thread(_deliver)
            logger.info("invite_email_sent", provider="smtp", to=payload.to_email)
            return True
        except Exception as exc:
            logger.warning(
                "invite_email_smtp_error",
                to=payload.to_email,
                error=str(exc),
            )
            return False
