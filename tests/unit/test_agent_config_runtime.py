from uuid import uuid4

from voxforge.config import Settings
from voxforge.core.domain.agent_config import AgentConfigVersion
from voxforge.modules.agent_config.application.runtime import (
    effective_orchestrator_mode,
    effective_system_prompt,
)
from voxforge.modules.conversation.application.engine import ConversationEngine


def test_effective_system_prompt_prefers_active_config():
    settings = Settings(system_prompt="default prompt")
    active = AgentConfigVersion(
        id=uuid4(),
        org_id=uuid4(),
        version=1,
        label="preset:test",
        prompt_config={"system_prompt": "custom support prompt"},
        orchestrator_config={},
        eval_thresholds={},
        is_active=True,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    assert effective_system_prompt(active, settings) == "custom support prompt"
    assert effective_system_prompt(None, settings) == "default prompt"


def test_effective_orchestrator_mode_prefers_active_config():
    settings = Settings(orchestrator_mode="single")
    active = AgentConfigVersion(
        id=uuid4(),
        org_id=uuid4(),
        version=1,
        label="preset:test",
        prompt_config={},
        orchestrator_config={"mode": "multi_agent"},
        eval_thresholds={},
        is_active=True,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    assert effective_orchestrator_mode(active, settings) == "multi_agent"


def test_effective_orchestrator_mode_prefers_session_config():
    settings = Settings(orchestrator_mode="single")
    active = AgentConfigVersion(
        id=uuid4(),
        org_id=uuid4(),
        version=1,
        label="preset:test",
        prompt_config={},
        orchestrator_config={"mode": "single"},
        eval_thresholds={},
        is_active=True,
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    assert (
        effective_orchestrator_mode(active, settings, session_config={"orchestrator": "multi_agent"})
        == "multi_agent"
    )


def test_conversation_engine_uses_session_system_prompt():
    settings = Settings(system_prompt="default", llm_provider="mock", openai_api_key="test")
    from voxforge.infrastructure.providers.llm.openai import OpenAILLMProvider

    engine = ConversationEngine(OpenAILLMProvider("test"), settings)
    session_id = uuid4()
    engine.set_session_system_prompt(session_id, "org-specific prompt")
    engine.init_session(session_id)
    assert engine._history[session_id][0].content == "org-specific prompt"
