from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.config import Settings, get_settings
from voxforge.core.domain.auth import Principal
from voxforge.core.events.bus import EventBus, get_event_bus
from voxforge.core.exceptions import ForbiddenError, UnauthorizedError
from voxforge.infrastructure.email.invite_mailer import InviteEmailSender
from voxforge.infrastructure.db.evaluation_repository import EvaluationRepository
from voxforge.infrastructure.db.dashboard_repository import DashboardRepository
from voxforge.infrastructure.db.handoff_repository import HandoffRepository
from voxforge.infrastructure.db.knowledge_repository import KnowledgeRepository
from voxforge.infrastructure.db.memory_repository import MemoryRepository
from voxforge.infrastructure.db.outcome_repository import OutcomeRepository
from voxforge.infrastructure.db.replay_repository import ReplayRepository
from voxforge.infrastructure.db.session import get_db_session
from voxforge.infrastructure.db.tool_repository import ToolCallRepository
from voxforge.infrastructure.http.rate_limit import enforce_authenticated_limits
from voxforge.infrastructure.knowledge.blob import create_blob_store
from voxforge.infrastructure.livekit.token_service import LiveKitTokenService
from voxforge.infrastructure.providers.embeddings.factory import create_embedding_provider
from voxforge.infrastructure.providers.factory import (
    create_llm_provider,
    create_stt_provider,
    create_tts_provider,
)
from voxforge.infrastructure.providers.llm.openai import OpenAILLMProvider
from voxforge.infrastructure.providers.support.factory import (
    create_ticketing_provider,
)
from voxforge.infrastructure.redis.client import get_redis
from voxforge.infrastructure.redis.session_state import RedisSessionStateStore
from voxforge.infrastructure.tools.mcp_runtime_registry import MCPRuntimeRegistry
from voxforge.infrastructure.tools.registry_factory import create_tool_registry
from voxforge.infrastructure.voice.programmatic_runner import ProgrammaticPipelineRunner
from voxforge.modules.agent_config.application.service import AgentConfigService
from voxforge.modules.alerts.application.service import AlertService
from voxforge.modules.auth.application.service import AuthService
from voxforge.modules.auth.application.sso_service import SamlConnectionService
from voxforge.modules.dashboard.application.service import DashboardService
from voxforge.modules.evaluation.application.service import EvaluationEngine
from voxforge.modules.handoff.application.orchestrator import HandoffOrchestrator
from voxforge.modules.handoff.application.policy import HandoffPolicyEngine
from voxforge.modules.handoff.application.replay_link import ReplayLinkService
from voxforge.modules.handoff.application.summarizer import ExtractiveConversationSummarizer
from voxforge.modules.knowledge.application.factory import create_knowledge_context_builder
from voxforge.modules.knowledge.application.ingestion_service import KnowledgeIngestionService
from voxforge.modules.knowledge.application.search_service import KnowledgeSearchService
from voxforge.modules.mcp_tool_router.application.router import ToolRouter
from voxforge.modules.memory.application.service import MemoryService
from voxforge.modules.onboarding.application.service import OnboardingService
from voxforge.modules.outcomes.application.service import OutcomeExtractionService
from voxforge.modules.replay.application.service import ReplayService
from voxforge.modules.session_manager.application.service import SessionManager
from voxforge.modules.voice_gateway.application.pipeline import VoicePipelineService

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_auth_service(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(db, settings)


def get_invite_email_sender(settings: Settings = Depends(get_settings)) -> InviteEmailSender:
    return InviteEmailSender(settings)


def get_saml_connection_service(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SamlConnectionService:
    return SamlConnectionService(db, settings)


def get_handoff_repository(
    db: AsyncSession = Depends(get_db_session),
) -> HandoffRepository:
    return HandoffRepository(db)


async def get_optional_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    api_key: Annotated[str | None, Security(api_key_header)],
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> Principal | None:
    if not settings.auth_required:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=500,
                detail="AUTH_REQUIRED must be enabled in production",
            )
        from uuid import UUID

        from voxforge.core.domain.auth import OrgRole, PrincipalType

        return Principal(
            type=PrincipalType.USER,
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            org_id=UUID("00000000-0000-0000-0000-000000000010"),
            role=OrgRole.OWNER,
        )

    if credentials and credentials.credentials:
        try:
            return await auth_service.resolve_principal_from_bearer(credentials.credentials)
        except UnauthorizedError:
            return None

    if api_key:
        try:
            return await auth_service.resolve_principal_from_api_key(api_key)
        except UnauthorizedError:
            return None

    cookie_token = request.cookies.get(settings.auth_cookie_name)
    if cookie_token:
        try:
            return await auth_service.resolve_principal_from_bearer(cookie_token)
        except UnauthorizedError:
            return None

    return None


async def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    api_key: Annotated[str | None, Security(api_key_header)],
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not settings.auth_required:
        if settings.app_env == "production":
            raise HTTPException(
                status_code=500,
                detail="AUTH_REQUIRED must be enabled in production",
            )
        from uuid import UUID

        from voxforge.core.domain.auth import OrgRole, PrincipalType

        return Principal(
            type=PrincipalType.USER,
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            org_id=UUID("00000000-0000-0000-0000-000000000010"),
            role=OrgRole.OWNER,
        )

    if credentials and credentials.credentials:
        try:
            return await auth_service.resolve_principal_from_bearer(credentials.credentials)
        except UnauthorizedError as exc:
            raise HTTPException(status_code=401, detail=exc.message) from exc

    if api_key:
        try:
            return await auth_service.resolve_principal_from_api_key(api_key)
        except UnauthorizedError as exc:
            raise HTTPException(status_code=401, detail=exc.message) from exc

    cookie_token = request.cookies.get(settings.auth_cookie_name)
    if cookie_token:
        try:
            return await auth_service.resolve_principal_from_bearer(cookie_token)
        except UnauthorizedError as exc:
            raise HTTPException(status_code=401, detail=exc.message) from exc

    raise HTTPException(status_code=401, detail="Authentication required")


def require_scope(scope: str):
    async def _checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        try:
            AuthService.require_scope(principal, scope)
        except ForbiddenError as exc:
            raise HTTPException(status_code=403, detail=exc.message) from exc
        return principal

    return _checker


def rate_limit_category(category: str):
    """Enforce org/session/user/api-key limits after authentication."""

    async def _enforce(
        request: Request,
        principal: Principal = Depends(get_current_principal),
        settings: Settings = Depends(get_settings),
    ) -> None:
        await enforce_authenticated_limits(
            path=request.url.path,
            settings=settings,
            category=category,
            org_id=str(principal.org_id),
            user_id=str(principal.user_id) if principal.user_id else None,
            api_key_id=str(principal.api_key_id) if principal.api_key_id else None,
        )

    return _enforce


def rate_limit_category_optional(category: str):
    """Org/session limits when principal is present (e.g. replay with JWT)."""

    async def _enforce(
        request: Request,
        principal: Principal | None = Depends(get_optional_principal),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if principal is None:
            return
        await enforce_authenticated_limits(
            path=request.url.path,
            settings=settings,
            category=category,
            org_id=str(principal.org_id),
            user_id=str(principal.user_id) if principal.user_id else None,
            api_key_id=str(principal.api_key_id) if principal.api_key_id else None,
        )

    return _enforce


def get_state_store(settings: Settings = Depends(get_settings)) -> RedisSessionStateStore:
    return RedisSessionStateStore(get_redis(), ttl_seconds=settings.session_state_ttl_seconds)


def get_session_manager(
    db: AsyncSession = Depends(get_db_session),
    state_store: RedisSessionStateStore = Depends(get_state_store),
    event_bus: EventBus = Depends(get_event_bus),
    settings: Settings = Depends(get_settings),
) -> SessionManager:
    return SessionManager(db, state_store, event_bus, settings)


def get_stt_provider(settings: Settings = Depends(get_settings)):
    return create_stt_provider(settings)


def get_llm_provider(settings: Settings = Depends(get_settings)):
    return create_llm_provider(settings)


def get_tts_provider(settings: Settings = Depends(get_settings)):
    return create_tts_provider(settings)


def get_livekit_service(settings: Settings = Depends(get_settings)) -> LiveKitTokenService:
    return LiveKitTokenService(settings)


def get_memory_service(
    db: AsyncSession = Depends(get_db_session),
    llm: OpenAILLMProvider = Depends(get_llm_provider),
    settings: Settings = Depends(get_settings),
) -> MemoryService | None:
    if not settings.memory_enabled:
        return None
    store = MemoryRepository(db)
    embedder = create_embedding_provider(settings)
    return MemoryService(store, embedder, settings, llm)


def get_knowledge_repository(
    db: AsyncSession = Depends(get_db_session),
) -> KnowledgeRepository:
    return KnowledgeRepository(db)


def get_knowledge_search_service(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeSearchService | None:
    if not settings.knowledge_enabled:
        return None
    return KnowledgeSearchService(
        KnowledgeRepository(db),
        create_embedding_provider(settings),
        settings,
    )


def get_knowledge_ingestion_service(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> KnowledgeIngestionService | None:
    if not settings.knowledge_enabled:
        return None
    blob = create_blob_store(
        settings.knowledge_blob_store,
        path=settings.knowledge_blob_path,
    )
    return KnowledgeIngestionService(
        KnowledgeRepository(db),
        blob,
        create_embedding_provider(settings),
        settings,
    )


def get_knowledge_context_builder(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
):
    return create_knowledge_context_builder(db, settings)


def get_mcp_registry(request: Request) -> MCPRuntimeRegistry | None:
    return getattr(request.app.state, "mcp_registry", None)


def get_voice_pipeline_bundle(
    db: AsyncSession = Depends(get_db_session),
    state_store: RedisSessionStateStore = Depends(get_state_store),
    event_bus: EventBus = Depends(get_event_bus),
    settings: Settings = Depends(get_settings),
    mcp_registry: MCPRuntimeRegistry | None = Depends(get_mcp_registry),
):
    """FastAPI entry into the shared voice composition root."""
    from voxforge.modules.voice_gateway.application.pipeline_factory import (
        build_voice_pipeline_bundle,
    )

    return build_voice_pipeline_bundle(
        db,
        state_store,
        event_bus,
        settings,
        mcp_registry=mcp_registry,
    )


def get_handoff_orchestrator(
    db: AsyncSession = Depends(get_db_session),
    session_manager: SessionManager = Depends(get_session_manager),
    settings: Settings = Depends(get_settings),
) -> HandoffOrchestrator | None:
    if not settings.handoff_enabled:
        return None
    return HandoffOrchestrator(
        HandoffRepository(db),
        create_ticketing_provider(settings),
        ExtractiveConversationSummarizer(session_manager),
        ReplayLinkService(settings),
        session_manager,
        settings,
    )


def get_handoff_policy_engine(
    settings: Settings = Depends(get_settings),
) -> HandoffPolicyEngine | None:
    if not settings.handoff_enabled or not settings.handoff_auto_policy:
        return None
    return HandoffPolicyEngine()


def get_tool_router(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    mcp_registry: MCPRuntimeRegistry | None = Depends(get_mcp_registry),
    handoff_orchestrator: HandoffOrchestrator | None = Depends(get_handoff_orchestrator),
) -> ToolRouter | None:
    if not settings.tools_enabled:
        return None
    registry = create_tool_registry(
        settings,
        mcp_registry=mcp_registry,
        handoff_orchestrator=handoff_orchestrator,
    )
    repo = ToolCallRepository(db)
    return ToolRouter(registry, settings, repo)


def get_evaluation_engine(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    llm=Depends(get_llm_provider),
) -> EvaluationEngine | None:
    if not settings.evaluation_enabled:
        return None
    return EvaluationEngine(EvaluationRepository(db), settings, llm)


def get_dashboard_service(
    db: AsyncSession = Depends(get_db_session),
) -> DashboardService:
    return DashboardService(DashboardRepository(db))


def get_onboarding_service(
    db: AsyncSession = Depends(get_db_session),
) -> OnboardingService:
    return OnboardingService(db)


def get_outcome_service(
    db: AsyncSession = Depends(get_db_session),
) -> OutcomeExtractionService:
    return OutcomeExtractionService(OutcomeRepository(db))


def get_replay_service(
    db: AsyncSession = Depends(get_db_session),
) -> ReplayService:
    return ReplayService(ReplayRepository(db))


def get_alert_service(
    db: AsyncSession = Depends(get_db_session),
) -> AlertService:
    return AlertService(db, DashboardRepository(db))


def get_agent_config_service(
    db: AsyncSession = Depends(get_db_session),
) -> AgentConfigService:
    return AgentConfigService(db)


def get_pipeline(
    bundle=Depends(get_voice_pipeline_bundle),
) -> VoicePipelineService:
    return bundle.pipeline


def get_onboarding_pipeline_runner(
    bundle=Depends(get_voice_pipeline_bundle),
) -> ProgrammaticPipelineRunner:
    return ProgrammaticPipelineRunner(bundle.pipeline, bundle=bundle)
