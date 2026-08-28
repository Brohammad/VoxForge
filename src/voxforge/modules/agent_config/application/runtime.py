"""Apply org-scoped agent config versions to live voice sessions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.config import Settings
from voxforge.core.domain.agent_config import AgentConfigVersion
from voxforge.infrastructure.db.agent_config_repository import AgentConfigRepository
from voxforge.modules.agent_orchestrator.application.factory import create_response_generator
from voxforge.modules.agent_orchestrator.application.service import AgentOrchestrator
from voxforge.modules.voice_gateway.application.pipeline import VoicePipelineService


def effective_system_prompt(active: AgentConfigVersion | None, settings: Settings) -> str:
    if active is not None:
        prompt = active.prompt_config.get("system_prompt")
        if isinstance(prompt, str) and prompt.strip():
            return prompt.strip()
    return settings.system_prompt


def effective_orchestrator_mode(
    active: AgentConfigVersion | None,
    settings: Settings,
    session_config: dict | None = None,
) -> str:
    if session_config:
        mode = session_config.get("orchestrator")
        if isinstance(mode, str) and mode.strip() in {"single", "multi_agent"}:
            return mode.strip()
    if active is not None:
        mode = active.orchestrator_config.get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode.strip()
    return settings.orchestrator_mode


async def load_active_agent_config(db: AsyncSession, org_id: UUID) -> AgentConfigVersion | None:
    return await AgentConfigRepository(db).get_active(org_id)


async def apply_active_agent_config(
    *,
    db: AsyncSession,
    org_id: UUID,
    session_id: UUID,
    pipeline: VoicePipelineService,
    response_generator: object,
    settings: Settings,
    llm: object | None,
    memory_service: object | None,
    tool_router: object | None,
    knowledge_context_builder: object | None,
    session_config: dict | None = None,
) -> object:
    """Swap generator mode if needed and set per-session system prompt from active config."""
    active = await load_active_agent_config(db, org_id)
    mode = effective_orchestrator_mode(active, settings, session_config=session_config)
    prompt = effective_system_prompt(active, settings)

    need_multi = mode == "multi_agent"
    is_multi = isinstance(response_generator, AgentOrchestrator)
    if need_multi != is_multi:
        effective_settings = settings.model_copy(
            update={"orchestrator_mode": mode, "system_prompt": prompt}
        )
        response_generator = create_response_generator(
            effective_settings,
            llm,
            memory_service,
            tool_router,
            knowledge_context_builder,
        )
        pipeline.set_response_generator(response_generator)

    if hasattr(response_generator, "set_session_system_prompt"):
        response_generator.set_session_system_prompt(session_id, prompt)

    return response_generator
