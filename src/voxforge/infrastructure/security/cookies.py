"""HttpOnly auth cookie helpers for browser sessions."""

from __future__ import annotations

from secrets import token_urlsafe

from fastapi import Response

from voxforge.config import Settings
from voxforge.core.domain.auth import TokenPair


def set_auth_cookies(response: Response, tokens: TokenPair, settings: Settings) -> None:
    if not settings.auth_cookies_enabled:
        return
    max_age = settings.jwt_access_token_expire_minutes * 60
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=tokens.access_token,
        max_age=max_age,
        httponly=True,
        secure=settings.auth_cookie_secure_effective,
        samesite=settings.auth_cookie_samesite,
        path="/",
        domain=settings.auth_cookie_domain or None,
    )
    refresh_max_age = settings.jwt_refresh_token_expire_days * 86400
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=tokens.refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=settings.auth_cookie_secure_effective,
        samesite=settings.auth_cookie_samesite,
        path="/api/v1/auth",
        domain=settings.auth_cookie_domain or None,
    )
    # Double-submit CSRF token (readable by JS; compared to X-CSRF-Token header).
    response.set_cookie(
        key=settings.auth_csrf_cookie_name,
        value=token_urlsafe(32),
        max_age=max_age,
        httponly=False,
        secure=settings.auth_cookie_secure_effective,
        samesite=settings.auth_cookie_samesite,
        path="/",
        domain=settings.auth_cookie_domain or None,
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        domain=settings.auth_cookie_domain or None,
    )
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        path="/api/v1/auth",
        domain=settings.auth_cookie_domain or None,
    )
    response.delete_cookie(
        key=settings.auth_csrf_cookie_name,
        path="/",
        domain=settings.auth_cookie_domain or None,
    )
