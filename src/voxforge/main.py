from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from voxforge.api.v1.router import api_v1_router
from voxforge.api.ws.livekit_proxy import router as livekit_proxy_router
from voxforge.api.ws.voice import router as ws_router
from voxforge.config import get_settings
from voxforge.core.exceptions import (
    ApiKeyNotFoundError,
    ForbiddenError,
    InvalidCredentialsError,
    OrganizationNotFoundError,
    PipelineError,
    ProviderError,
    SamlAssertionError,
    SamlConnectionNotFoundError,
    SessionNotFoundError,
    SessionStateError,
    UnauthorizedError,
    UserNotFoundError,
    VoxForgeError,
)
from voxforge.infrastructure.db.session import close_db, init_db
from voxforge.infrastructure.http.csrf import CsrfMiddleware
from voxforge.infrastructure.http.rate_limit import RateLimitMiddleware
from voxforge.infrastructure.http.request_context import RequestContextMiddleware
from voxforge.infrastructure.http.security_headers import SecurityHeadersMiddleware
from voxforge.infrastructure.observability.logging import setup_logging
from voxforge.infrastructure.observability.telemetry import setup_telemetry
from voxforge.infrastructure.redis.client import close_redis, init_redis
from voxforge.infrastructure.security.production import (
    log_startup_security_warnings,
    validate_production_settings,
)
from voxforge.infrastructure.tools.mcp_runtime_registry import MCPRuntimeRegistry
from voxforge.infrastructure.tools.registry_factory import register_support_tool_discovery

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"
LIVEKIT_EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "livekit-client"
PUBLIC_DIR = Path(__file__).resolve().parents[2] / "public"

_ERROR_STATUS_CODES: dict[type[VoxForgeError], int] = {
    UnauthorizedError: 401,
    InvalidCredentialsError: 401,
    ForbiddenError: 403,
    SessionNotFoundError: 404,
    UserNotFoundError: 404,
    OrganizationNotFoundError: 404,
    ApiKeyNotFoundError: 404,
    SamlConnectionNotFoundError: 404,
    SamlAssertionError: 400,
    SessionStateError: 409,
    ProviderError: 502,
    PipelineError: 500,
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    validate_production_settings(settings)
    log_startup_security_warnings(settings)
    setup_logging(settings.log_level)
    setup_telemetry(settings)
    await init_db(settings.database_url)
    await init_redis(settings.redis_url)

    mcp_registry: MCPRuntimeRegistry | None = None
    if settings.tools_enabled:
        mcp_registry = MCPRuntimeRegistry(settings)
        if settings.mcp_servers_config.strip() and settings.mcp_startup_discover:
            await mcp_registry.discover_all()
        register_support_tool_discovery(settings, mcp_registry)
    app.state.mcp_registry = mcp_registry

    yield
    await close_redis()
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="VoxForge",
        description="Production-grade Voice AI Infrastructure Platform",
        version="1.0.0-rc.1",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )

    if settings.trusted_host_list:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(CsrfMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)

    @app.exception_handler(VoxForgeError)
    async def voxforge_error_handler(_request: Request, exc: VoxForgeError) -> JSONResponse:
        status = 400
        for exc_type, code in _ERROR_STATUS_CODES.items():
            if isinstance(exc, exc_type):
                status = code
                break
        return JSONResponse(
            status_code=status,
            content={"detail": exc.message, "code": exc.code},
        )

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    if not getattr(app, "_otel_instrumented", False):
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="/api/v1/health,/api/v1/ready,/api/v1/metrics",
        )
        app._otel_instrumented = True  # type: ignore[attr-defined]

    app.include_router(api_v1_router, prefix="/api/v1")
    app.include_router(ws_router)
    app.include_router(livekit_proxy_router)

    if PUBLIC_DIR.is_dir():
        app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public-static")

        @app.get("/")
        async def landing_page() -> FileResponse:
            return FileResponse(PUBLIC_DIR / "landing" / "index.html")

        @app.get("/demo")
        async def demo_page() -> FileResponse:
            return FileResponse(
                PUBLIC_DIR / "demo" / "index.html",
                headers={"Cache-Control": "no-store"},
            )

    if DASHBOARD_DIR.is_dir():
        app.mount(
            "/dashboard/static",
            StaticFiles(directory=DASHBOARD_DIR / "static"),
            name="dashboard-static",
        )

        @app.get("/dashboard")
        async def dashboard_ui() -> FileResponse:
            return FileResponse(DASHBOARD_DIR / "index.html")

    if LIVEKIT_EXAMPLE_DIR.is_dir():
        app.mount(
            "/examples/livekit/static",
            StaticFiles(directory=LIVEKIT_EXAMPLE_DIR / "static"),
            name="livekit-example-static",
        )

        @app.get("/examples/livekit")
        async def livekit_example_ui() -> FileResponse:
            return FileResponse(LIVEKIT_EXAMPLE_DIR / "index.html")

    app.state.settings = settings
    return app


app = create_app()
