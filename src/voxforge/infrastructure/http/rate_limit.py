"""Redis-backed HTTP rate limiting with category policies and layered dimensions."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request, WebSocket
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from voxforge.config import Settings, get_settings
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.observability.metrics import (
    rate_limit_allowed_total,
    rate_limit_blocked_total,
    rate_limit_redis_errors_total,
)
from voxforge.infrastructure.redis.client import get_redis

logger = get_logger(__name__)

FailMode = Literal["open", "closed"]
Dimension = Literal["ip", "user", "org", "api_key", "session"]

_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/health",
        "/api/v1/ready",
        "/api/v1/metrics",
        "/api/v1/docs",
        "/api/v1/redoc",
        "/api/v1/openapi.json",
    }
)

_SESSION_ID_RE = re.compile(r"/api/v1/(?:sessions|livekit/sessions)/([0-9a-fA-F-]{36})")


@dataclass(frozen=True)
class RateLimitPolicy:
    """Category policy for sustained (per minute) and burst (per 10s) limits."""

    category: str
    path_prefixes: tuple[str, ...] = ()
    path_regex: re.Pattern[str] | None = None
    methods: frozenset[str] | None = None
    sustained_per_minute: int = 60
    burst_per_10_seconds: int = 10
    fail_mode: FailMode = "open"
    org_sustained_per_minute: int | None = None
    org_burst_per_10_seconds: int | None = None
    session_sustained_per_minute: int | None = None
    session_burst_per_10_seconds: int | None = None

    def matches(self, method: str, path: str) -> bool:
        if self.methods is not None and method.upper() not in self.methods:
            return False
        if self.path_regex is not None and self.path_regex.search(path):
            return True
        return any(path.startswith(prefix) for prefix in self.path_prefixes)


# Ordered — first match wins. More specific rules precede broad prefixes.
RATE_LIMIT_POLICIES: tuple[RateLimitPolicy, ...] = (
    RateLimitPolicy(
        category="auth_login",
        path_prefixes=("/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"),
        methods=frozenset({"POST"}),
        sustained_per_minute=20,
        burst_per_10_seconds=5,
        fail_mode="closed",
    ),
    RateLimitPolicy(
        category="auth",
        path_prefixes=("/api/v1/auth",),
        sustained_per_minute=40,
        burst_per_10_seconds=10,
        fail_mode="closed",
    ),
    RateLimitPolicy(
        category="demo",
        path_prefixes=("/api/v1/demo",),
        # Local client demos: chat + hear per turn; keep headroom for retries.
        sustained_per_minute=120,
        burst_per_10_seconds=30,
        fail_mode="closed",
    ),
    RateLimitPolicy(
        category="api_keys",
        path_prefixes=("/api/v1/api-keys",),
        methods=frozenset({"POST"}),
        sustained_per_minute=10,
        burst_per_10_seconds=3,
        fail_mode="closed",
        org_sustained_per_minute=20,
        org_burst_per_10_seconds=5,
    ),
    RateLimitPolicy(
        category="sessions_create",
        path_prefixes=("/api/v1/sessions",),
        methods=frozenset({"POST"}),
        sustained_per_minute=30,
        burst_per_10_seconds=5,
        fail_mode="closed",
        org_sustained_per_minute=100,
        org_burst_per_10_seconds=20,
    ),
    RateLimitPolicy(
        category="voice_ws",
        path_prefixes=("/api/v1/ws/voice",),
        sustained_per_minute=20,
        burst_per_10_seconds=5,
        fail_mode="closed",
        org_sustained_per_minute=60,
        org_burst_per_10_seconds=15,
    ),
    RateLimitPolicy(
        category="livekit",
        path_prefixes=("/api/v1/livekit",),
        methods=frozenset({"POST"}),
        sustained_per_minute=30,
        burst_per_10_seconds=5,
        fail_mode="closed",
        org_sustained_per_minute=80,
        org_burst_per_10_seconds=15,
        session_sustained_per_minute=20,
        session_burst_per_10_seconds=5,
    ),
    RateLimitPolicy(
        category="knowledge_upload",
        path_regex=re.compile(r"^/api/v1/knowledge/collections/[^/]+/documents$"),
        methods=frozenset({"POST"}),
        sustained_per_minute=10,
        burst_per_10_seconds=2,
        fail_mode="closed",
        org_sustained_per_minute=30,
        org_burst_per_10_seconds=5,
    ),
    RateLimitPolicy(
        category="knowledge_reindex",
        path_regex=re.compile(r"^/api/v1/knowledge/documents/[^/]+/reindex$"),
        methods=frozenset({"POST"}),
        sustained_per_minute=5,
        burst_per_10_seconds=2,
        fail_mode="closed",
        org_sustained_per_minute=20,
        org_burst_per_10_seconds=5,
    ),
    RateLimitPolicy(
        category="knowledge_search",
        path_prefixes=("/api/v1/knowledge/search",),
        methods=frozenset({"POST"}),
        sustained_per_minute=60,
        burst_per_10_seconds=15,
        fail_mode="open",
        org_sustained_per_minute=200,
        org_burst_per_10_seconds=40,
    ),
    RateLimitPolicy(
        category="knowledge_collections",
        path_prefixes=("/api/v1/knowledge/collections",),
        methods=frozenset({"POST"}),
        sustained_per_minute=20,
        burst_per_10_seconds=5,
        fail_mode="closed",
        org_sustained_per_minute=50,
        org_burst_per_10_seconds=10,
    ),
    RateLimitPolicy(
        category="memory_search",
        path_regex=re.compile(r"^/api/v1/sessions/[^/]+/memory/search$"),
        methods=frozenset({"POST"}),
        sustained_per_minute=60,
        burst_per_10_seconds=15,
        fail_mode="open",
        org_sustained_per_minute=200,
        org_burst_per_10_seconds=40,
    ),
    RateLimitPolicy(
        category="replay",
        path_regex=re.compile(r"^/api/v1/sessions/[^/]+/replay$"),
        methods=frozenset({"GET"}),
        sustained_per_minute=30,
        burst_per_10_seconds=10,
        fail_mode="closed",
        org_sustained_per_minute=100,
        org_burst_per_10_seconds=25,
        session_sustained_per_minute=15,
        session_burst_per_10_seconds=5,
    ),
    RateLimitPolicy(
        category="onboarding_sample",
        path_prefixes=("/api/v1/onboarding/run-sample-call",),
        methods=frozenset({"POST"}),
        sustained_per_minute=5,
        burst_per_10_seconds=2,
        fail_mode="closed",
        org_sustained_per_minute=15,
        org_burst_per_10_seconds=3,
    ),
    RateLimitPolicy(
        category="onboarding",
        path_prefixes=("/api/v1/onboarding",),
        sustained_per_minute=30,
        burst_per_10_seconds=8,
        fail_mode="closed",
        org_sustained_per_minute=60,
        org_burst_per_10_seconds=15,
    ),
    RateLimitPolicy(
        category="dashboard",
        path_prefixes=("/api/v1/dashboard",),
        methods=frozenset({"GET"}),
        sustained_per_minute=120,
        burst_per_10_seconds=30,
        fail_mode="open",
        org_sustained_per_minute=300,
        org_burst_per_10_seconds=60,
    ),
    RateLimitPolicy(
        category="sessions",
        path_prefixes=("/api/v1/sessions",),
        sustained_per_minute=120,
        burst_per_10_seconds=30,
        fail_mode="open",
        org_sustained_per_minute=300,
        org_burst_per_10_seconds=60,
        session_sustained_per_minute=60,
        session_burst_per_10_seconds=15,
    ),
    RateLimitPolicy(
        category="api_default",
        path_prefixes=("/api/v1/",),
        sustained_per_minute=120,
        burst_per_10_seconds=30,
        fail_mode="open",
        org_sustained_per_minute=500,
        org_burst_per_10_seconds=100,
    ),
)


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    blocked: bool = False
    redis_error: bool = False
    dimension: str = "ip"
    category: str = ""


def get_client_ip(request: Request | WebSocket) -> str:
    if isinstance(request, WebSocket):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def extract_session_id(path: str) -> str | None:
    match = _SESSION_ID_RE.search(path)
    return match.group(1) if match else None


def resolve_policy(method: str, path: str) -> RateLimitPolicy | None:
    if path in _EXEMPT_PATHS:
        return None
    if not path.startswith("/api/v1"):
        return None
    for policy in RATE_LIMIT_POLICIES:
        if policy.matches(method, path):
            return policy
    return None


def get_policy_by_category(category: str) -> RateLimitPolicy:
    for policy in RATE_LIMIT_POLICIES:
        if policy.category == category:
            return policy
    raise KeyError(f"Unknown rate limit category: {category}")


def _scaled(value: int, multiplier: float) -> int:
    return max(1, int(value * multiplier))


class RateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._fail_closed = settings.rate_limit_fail_closed_categories_set

    def _effective_fail_mode(self, policy: RateLimitPolicy) -> FailMode:
        if policy.category in self._fail_closed:
            return "closed"
        return policy.fail_mode

    async def check(
        self,
        *,
        policy: RateLimitPolicy,
        dimension: Dimension,
        identifier: str,
        path: str,
        sustained_limit: int,
        burst_limit: int,
    ) -> RateLimitResult:
        if not self._settings.rate_limit_enabled:
            return RateLimitResult(allowed=True, category=policy.category, dimension=dimension)

        multiplier = self._settings.rate_limit_multiplier
        sustained = _scaled(sustained_limit, multiplier)
        burst = _scaled(burst_limit, multiplier)
        fail_mode = self._effective_fail_mode(policy)

        try:
            redis = get_redis()
            now = int(time.time())
            burst_bucket = now // 10
            sustained_bucket = now // 60

            burst_key = f"ratelimit:burst:{dimension}:{identifier}:{policy.category}:{burst_bucket}"
            sustained_key = (
                f"ratelimit:sustained:{dimension}:{identifier}:{policy.category}:{sustained_bucket}"
            )

            burst_count = await redis.incr(burst_key)
            if burst_count == 1:
                await redis.expire(burst_key, 15)
            sustained_count = await redis.incr(sustained_key)
            if sustained_count == 1:
                await redis.expire(sustained_key, 70)

            if burst_count > burst or sustained_count > sustained:
                rate_limit_blocked_total.labels(category=policy.category, dimension=dimension).inc()
                logger.warning(
                    "rate_limit_exceeded",
                    category=policy.category,
                    dimension=dimension,
                    identifier=identifier,
                    path=path,
                    burst_count=burst_count,
                    sustained_count=sustained_count,
                )
                return RateLimitResult(
                    allowed=False,
                    blocked=True,
                    category=policy.category,
                    dimension=dimension,
                )

            rate_limit_allowed_total.labels(category=policy.category, dimension=dimension).inc()
            return RateLimitResult(allowed=True, category=policy.category, dimension=dimension)
        except Exception as exc:
            rate_limit_redis_errors_total.labels(
                category=policy.category,
                fail_mode=fail_mode,
            ).inc()
            logger.warning(
                "rate_limit_redis_error",
                category=policy.category,
                dimension=dimension,
                error=str(exc),
                fail_mode=fail_mode,
            )
            if fail_mode == "closed":
                return RateLimitResult(
                    allowed=False,
                    redis_error=True,
                    category=policy.category,
                    dimension=dimension,
                )
            return RateLimitResult(
                allowed=True,
                redis_error=True,
                category=policy.category,
                dimension=dimension,
            )

    async def check_ip(self, policy: RateLimitPolicy, client_ip: str, path: str) -> RateLimitResult:
        return await self.check(
            policy=policy,
            dimension="ip",
            identifier=client_ip,
            path=path,
            sustained_limit=policy.sustained_per_minute,
            burst_limit=policy.burst_per_10_seconds,
        )

    async def check_org(
        self, policy: RateLimitPolicy, org_id: str, path: str
    ) -> RateLimitResult | None:
        if policy.org_sustained_per_minute is None:
            return None
        return await self.check(
            policy=policy,
            dimension="org",
            identifier=org_id,
            path=path,
            sustained_limit=policy.org_sustained_per_minute,
            burst_limit=policy.org_burst_per_10_seconds or policy.burst_per_10_seconds,
        )

    async def check_session(
        self, policy: RateLimitPolicy, session_id: str, path: str
    ) -> RateLimitResult | None:
        if policy.session_sustained_per_minute is None:
            return None
        return await self.check(
            policy=policy,
            dimension="session",
            identifier=session_id,
            path=path,
            sustained_limit=policy.session_sustained_per_minute,
            burst_limit=policy.session_burst_per_10_seconds or policy.burst_per_10_seconds,
        )


def _limiter(settings: Settings) -> RateLimiter:
    return RateLimiter(settings)


def _raise_or_response(result: RateLimitResult) -> None:
    if result.blocked:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again shortly.",
        )
    if result.redis_error:
        raise HTTPException(
            status_code=503,
            detail="Rate limiting temporarily unavailable. Try again shortly.",
        )


async def enforce_authenticated_limits(
    *,
    path: str,
    settings: Settings,
    category: str,
    org_id: str,
    user_id: str | None = None,
    api_key_id: str | None = None,
) -> None:
    if not settings.rate_limit_enabled:
        return
    policy = get_policy_by_category(category)
    limiter = _limiter(settings)

    org_result = await limiter.check_org(policy, org_id, path)
    if org_result is not None:
        _raise_or_response(org_result)

    session_id = extract_session_id(path)
    if session_id:
        session_result = await limiter.check_session(policy, session_id, path)
        if session_result is not None:
            _raise_or_response(session_result)

    if user_id:
        user_result = await limiter.check(
            policy=policy,
            dimension="user",
            identifier=user_id,
            path=path,
            sustained_limit=policy.org_sustained_per_minute or policy.sustained_per_minute,
            burst_limit=policy.org_burst_per_10_seconds or policy.burst_per_10_seconds,
        )
        _raise_or_response(user_result)

    if api_key_id:
        key_result = await limiter.check(
            policy=policy,
            dimension="api_key",
            identifier=api_key_id,
            path=path,
            sustained_limit=policy.org_sustained_per_minute or policy.sustained_per_minute,
            burst_limit=policy.org_burst_per_10_seconds or policy.burst_per_10_seconds,
        )
        _raise_or_response(key_result)


async def enforce_ws_connect_limit(
    websocket: WebSocket,
    *,
    settings: Settings,
    org_id: str | None = None,
) -> RateLimitResult:
    policy = get_policy_by_category("voice_ws")
    limiter = _limiter(settings)
    path = websocket.url.path
    client_ip = get_client_ip(websocket)

    ip_result = await limiter.check_ip(policy, client_ip, path)
    if not ip_result.allowed:
        return ip_result

    if org_id:
        org_result = await limiter.check_org(policy, org_id, path)
        if org_result is not None and not org_result.allowed:
            return org_result

    return RateLimitResult(allowed=True, category=policy.category)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return await call_next(request)

        policy = resolve_policy(request.method, request.url.path)
        if policy is None:
            return await call_next(request)

        client_ip = get_client_ip(request)
        limiter = RateLimiter(settings)
        result = await limiter.check_ip(policy, client_ip, request.url.path)

        if result.blocked:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again shortly."},
            )
        if result.redis_error:
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate limiting temporarily unavailable. Try again shortly."},
            )

        return await call_next(request)
