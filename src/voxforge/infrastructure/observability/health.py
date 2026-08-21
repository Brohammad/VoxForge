"""Readiness and dependency health checks."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from voxforge.config import Settings
from voxforge.infrastructure.db.session import get_engine
from voxforge.infrastructure.redis.client import get_redis
from voxforge.infrastructure.tools.mcp_runtime_registry import MCPRuntimeRegistry

KNOWLEDGE_WORKER_HEARTBEAT_KEY = "voxforge:knowledge_worker:heartbeat"
CHECK_TIMEOUT_SECONDS = 2.0


@dataclass
class HealthReport:
    status: str  # ok | degraded | unavailable
    checks: dict[str, str] = field(default_factory=dict)
    http_status: int = 200

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, **self.checks}


async def _check_database() -> str:
    engine = get_engine()
    async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    return "ok"


async def _check_redis() -> str:
    redis = get_redis()
    async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
        pong = await redis.ping()
    return "ok" if pong else "error: ping failed"


async def _check_knowledge_worker(settings: Settings) -> str:
    if not settings.knowledge_enabled:
        return "disabled"
    if not settings.knowledge_worker_enabled:
        return "disabled"
    try:
        redis = get_redis()
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            heartbeat = await redis.get(KNOWLEDGE_WORKER_HEARTBEAT_KEY)
        if heartbeat is None:
            return "error: no heartbeat"
        age = time.time() - float(heartbeat)
        if age > settings.knowledge_worker_heartbeat_stale_seconds:
            return f"error: heartbeat stale ({int(age)}s)"
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


def _check_livekit(settings: Settings) -> str:
    if not settings.livekit_url.strip():
        return "disabled"
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        return "error: missing credentials"
    return "configured"


def _check_mcp_registry(registry: MCPRuntimeRegistry | None, settings: Settings) -> str:
    if not settings.tools_enabled:
        return "disabled"
    if registry is None:
        return "disabled"
    health = registry.get_health()
    if health.status == "idle":
        return "ok"
    if health.status == "healthy":
        return "ok"
    if health.status == "degraded":
        return "degraded"
    return "error: all servers offline"


def _check_embedding_provider(settings: Settings) -> str:
    provider = settings.embedding_provider.lower()
    if provider == "mock":
        return "ok"
    if provider == "openai" and settings.openai_api_key:
        return "configured"
    return "error: missing credentials"


def _check_llm_provider(settings: Settings) -> str:
    provider = settings.llm_provider.lower()
    if provider == "mock":
        return "ok"
    if provider == "openai" and settings.openai_api_key:
        return "configured"
    return "error: missing credentials"


def _aggregate_status(checks: dict[str, str], *, fail_on_degraded: bool = False) -> tuple[str, int]:
    """Return (status, http_status). Critical: database, redis.

    By default degraded optional deps still return HTTP 200 so load balancers
    that only check status codes keep serving. Set READY_FAIL_ON_DEGRADED=true
    to treat soft failures as 503.
    """
    critical = ("database", "redis")
    for name in critical:
        if checks.get(name) != "ok":
            return "unavailable", 503

    has_degraded = any(
        checks.get(k) == "degraded"
        or (checks.get(k, "").startswith("error:") and k not in critical)
        for k in checks
    )
    if has_degraded:
        return "degraded", 503 if fail_on_degraded else 200
    return "ok", 200


async def run_readiness_checks(
    settings: Settings,
    *,
    mcp_registry: MCPRuntimeRegistry | None = None,
) -> HealthReport:
    checks: dict[str, str] = {}

    for name, coro in (
        ("database", _check_database()),
        ("redis", _check_redis()),
        ("knowledge_worker", _check_knowledge_worker(settings)),
    ):
        try:
            checks[name] = await coro
        except TimeoutError:
            checks[name] = "error: timeout"
        except Exception as exc:
            checks[name] = f"error: {exc}"

    checks["livekit"] = _check_livekit(settings)
    checks["mcp_registry"] = _check_mcp_registry(mcp_registry, settings)
    checks["embedding_provider"] = _check_embedding_provider(settings)
    checks["llm_provider"] = _check_llm_provider(settings)

    status, http_status = _aggregate_status(
        checks, fail_on_degraded=settings.ready_fail_on_degraded
    )
    return HealthReport(status=status, checks=checks, http_status=http_status)
