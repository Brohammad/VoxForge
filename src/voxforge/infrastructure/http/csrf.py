"""CSRF protection for cookie-authenticated browser sessions."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from voxforge.config import Settings

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_EXEMPT_SUFFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/auth/invites/accept",
    "/api/v1/demo/quickstart",
    "/api/v1/demo/speak",
    "/api/v1/demo/hear",
    "/api/v1/demo/chat",
)
_EXEMPT_CONTAINS = (
    "/sso/saml/acs",
)


class CsrfMiddleware(BaseHTTPMiddleware):
    """Require X-CSRF-Token when mutating with a session cookie and no Bearer/API key."""

    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._settings.auth_cookies_enabled:
            return await call_next(request)
        if request.method in _SAFE_METHODS:
            return await call_next(request)
        path = request.url.path.rstrip("/") or "/"
        if any(path.endswith(s.rstrip("/")) or path == s for s in _EXEMPT_SUFFIXES):
            return await call_next(request)
        if any(fragment in path for fragment in _EXEMPT_CONTAINS):
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return await call_next(request)
        if request.headers.get("x-api-key"):
            return await call_next(request)

        session_cookie = request.cookies.get(self._settings.auth_cookie_name)
        if not session_cookie:
            return await call_next(request)

        csrf_cookie = request.cookies.get(self._settings.auth_csrf_cookie_name)
        csrf_header = request.headers.get(self._settings.auth_csrf_header_name)
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid", "code": "csrf_failed"},
            )
        return await call_next(request)
