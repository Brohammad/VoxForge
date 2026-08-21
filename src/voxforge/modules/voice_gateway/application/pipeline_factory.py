"""Shared VoicePipelineService wiring for WebSocket, LiveKit, and REST onboarding."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.config import Settings
from voxforge.core.events.bus import EventBus
from voxforge.infrastructure.db.evaluation_repository import EvaluationRepository
from voxforge.infrastructure.db.handoff_repository import HandoffRepository
from voxforge.infrastructure.db.memory_repository import MemoryRepository
from voxforge.infrastructure.db.outcome_repository import OutcomeRepository
from voxforge.infrastructure.db.tool_repository import ToolCallRepository
from voxforge.infrastructure.providers.embeddings.factory import create_embedding_provider
from voxforge.infrastructure.providers.factory import (
    create_llm_provider,
    create_stt_provider,
    create_tts_provider,
)
from voxforge.infrastructure.providers.support.factory import create_ticketing_provider
from voxforge.infrastructure.redis.session_state import RedisSessionStateStore
from voxforge.infrastructure.tools.mcp_runtime_registry import MCPRuntimeRegistry
from voxforge.infrastructure.tools.registry_factory import create_tool_registry
from voxforge.modules.agent_orchestrator.application.factory import create_response_generator
from voxforge.modules.evaluation.application.service import EvaluationEngine
from voxforge.modules.handoff.application.orchestrator import HandoffOrchestrator
from voxforge.modules.handoff.application.policy import HandoffPolicyEngine
from voxforge.modules.handoff.application.replay_link import ReplayLinkService
from voxforge.modules.handoff.application.summarizer import ExtractiveConversationSummarizer
from voxforge.modules.knowledge.application.factory import create_knowledge_context_builder
from voxforge.modules.mcp_tool_router.application.router import ToolRouter
from voxforge.modules.memory.application.service import MemoryService
from voxforge.modules.outcomes.application.service import OutcomeExtractionService
from voxforge.modules.session_manager.application.service import SessionManager
from voxforge.modules.voice_gateway.application.pipeline import VoicePipelineService


@dataclass
class VoicePipelineBundle:
    session_manager: SessionManager
    pipeline: VoicePipelineService
    response_generator: object
    settings: Settings
    llm: object
    memory_service: MemoryService | None = None
    handoff_orchestrator: HandoffOrchestrator | None = None
    tool_router: ToolRouter | None = None
    knowledge_context_builder: object | None = None

    async def bootstrap_session_agent_config(self, org_id: UUID, session_id: UUID) -> object:
        from voxforge.modules.agent_config.application.runtime import apply_active_agent_config

        self.response_generator = await apply_active_agent_config(
            db=self.session_manager.db_session,
            org_id=org_id,
            session_id=session_id,
            pipeline=self.pipeline,
            response_generator=self.response_generator,
            settings=self.settings,
            llm=self.llm,
            memory_service=self.memory_service,
            tool_router=self.tool_router,
            knowledge_context_builder=self.knowledge_context_builder,
        )
        return self.response_generator


def build_voice_pipeline_bundle(
    db_session: AsyncSession,
    state_store: RedisSessionStateStore,
    event_bus: EventBus,
    settings: Settings,
    *,
    mcp_registry: MCPRuntimeRegistry | None = None,
) -> VoicePipelineBundle:
    """Single composition root for the voice critical path."""
    session_manager = SessionManager(db_session, state_store, event_bus, settings)
    stt = create_stt_provider(settings)
    llm = create_llm_provider(settings)

    handoff_orchestrator: HandoffOrchestrator | None = None
    handoff_policy: HandoffPolicyEngine | None = None
    if settings.handoff_enabled:
        handoff_orchestrator = HandoffOrchestrator(
            HandoffRepository(db_session),
            create_ticketing_provider(settings),
            ExtractiveConversationSummarizer(session_manager),
            ReplayLinkService(settings),
            session_manager,
            settings,
        )
        if settings.handoff_auto_policy:
            handoff_policy = HandoffPolicyEngine()

    memory_service: MemoryService | None = None
    if settings.memory_enabled:
        memory_service = MemoryService(
            MemoryRepository(db_session),
            create_embedding_provider(settings),
            settings,
            llm,
        )

    tool_router: ToolRouter | None = None
    if settings.tools_enabled:
        tool_router = ToolRouter(
            create_tool_registry(
                settings,
                mcp_registry=mcp_registry,
                handoff_orchestrator=handoff_orchestrator,
            ),
            settings,
            ToolCallRepository(db_session),
        )

    knowledge_context_builder = create_knowledge_context_builder(db_session, settings)

    response_generator = create_response_generator(
        settings,
        llm,
        memory_service,
        tool_router,
        knowledge_context_builder,
    )

    evaluation_engine: EvaluationEngine | None = None
    if settings.evaluation_enabled:
        evaluation_engine = EvaluationEngine(EvaluationRepository(db_session), settings, llm)

    outcome_service = OutcomeExtractionService(OutcomeRepository(db_session))
    tts = create_tts_provider(settings)

    pipeline = VoicePipelineService(
        session_manager,
        stt,
        response_generator,
        tts,
        settings,
        memory_service,
        evaluation_engine,
        outcome_service,
        handoff_orchestrator=handoff_orchestrator,
        handoff_policy=handoff_policy,
        knowledge_context_builder=knowledge_context_builder,
    )
    return VoicePipelineBundle(
        session_manager=session_manager,
        pipeline=pipeline,
        response_generator=response_generator,
        settings=settings,
        llm=llm,
        memory_service=memory_service,
        handoff_orchestrator=handoff_orchestrator,
        tool_router=tool_router,
        knowledge_context_builder=knowledge_context_builder,
    )
