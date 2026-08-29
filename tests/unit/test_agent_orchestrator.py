from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from voxforge.config import Settings
from voxforge.modules.agent_orchestrator.application.factory import create_response_generator
from voxforge.modules.agent_orchestrator.application.service import AgentOrchestrator
from voxforge.modules.conversation.application.engine import ConversationEngine


@pytest.fixture
def settings():
    return Settings(orchestrator_mode="single", openai_api_key="test-key")


def test_factory_single_mode(settings):
    gen = create_response_generator(settings)
    assert isinstance(gen, ConversationEngine)


def test_factory_multi_agent_mode():
    settings = Settings(orchestrator_mode="multi_agent", openai_api_key="test-key")
    gen = create_response_generator(settings)
    assert isinstance(gen, AgentOrchestrator)


def test_factory_multi_agent_mock_llm_still_uses_orchestrator():
    settings = Settings(orchestrator_mode="multi_agent", llm_provider="mock")
    gen = create_response_generator(settings)
    assert isinstance(gen, AgentOrchestrator)


@pytest.mark.asyncio
async def test_agent_orchestrator_streams_final_response():
    settings = Settings(orchestrator_mode="multi_agent", openai_api_key="test-key")
    orchestrator = AgentOrchestrator(settings)
    session_id = uuid4()
    orchestrator.init_session(session_id)
    orchestrator.add_user_message(session_id, "Hello")

    mock_result = {
        "final_response": "Hi there friend",
        "draft_response": "Hi there friend",
        "agent_trace": [
            {"agent": "planner", "status": "completed", "summary": "plan"},
            {"agent": "coordinator", "status": "completed", "summary": "Hi there friend"},
        ],
    }

    steps: list[tuple[str, str]] = []

    async def on_step(agent: str, status: str, payload: dict) -> None:
        steps.append((agent, status))

    with patch.object(
        orchestrator._graph, "ainvoke", new_callable=AsyncMock, return_value=mock_result
    ):
        tokens = []
        async for event in orchestrator.generate_response(session_id, on_agent_step=on_step):
            if event.text:
                tokens.append(event.text)

    assert "".join(tokens).strip() == "Hi there friend"
    assert len(steps) == 2
    assert orchestrator.get_last_agent_trace(session_id)


@pytest.mark.asyncio
async def test_agent_orchestrator_safety_block():
    settings = Settings(orchestrator_mode="multi_agent", openai_api_key="test-key")
    orchestrator = AgentOrchestrator(settings)
    session_id = uuid4()
    orchestrator.init_session(session_id)
    orchestrator.add_user_message(session_id, "Do something harmful")

    mock_result = {
        "final_response": "I'm sorry, but I can't help with that request.",
        "agent_trace": [{"agent": "safety", "status": "blocked", "summary": "unsafe"}],
    }

    with patch.object(
        orchestrator._graph, "ainvoke", new_callable=AsyncMock, return_value=mock_result
    ):
        tokens = []
        async for event in orchestrator.generate_response(session_id):
            if event.text:
                tokens.append(event.text)

    assert "sorry" in "".join(tokens).lower()


@pytest.mark.asyncio
async def test_mock_orchestrator_runs_knowledge_tool():
    from voxforge.core.domain.tools import ToolCallStatus, ToolDefinition, ToolResult
    from voxforge.infrastructure.providers.mock import MockLLMProvider

    class _Router:
        def list_tools(self):
            return [ToolDefinition(name="knowledge_base_lookup", description="kb", parameters={})]

        async def execute(self, name, args, **kwargs):
            return ToolResult(
                tool_name=name,
                output='{"articles":[{"title":"Refunds"}]}',
                status=ToolCallStatus.SUCCESS,
            )

    settings = Settings(orchestrator_mode="multi_agent", llm_provider="mock")
    orchestrator = AgentOrchestrator(settings, tool_router=_Router(), llm=MockLLMProvider())
    session_id = uuid4()
    orchestrator.init_session(session_id)
    orchestrator.add_user_message(session_id, "What is your refund policy?")
    tokens = []
    async for event in orchestrator.generate_response(session_id):
        if event.text:
            tokens.append(event.text)
    assert "refund" in "".join(tokens).lower()
    agents = [step["agent"] for step in orchestrator.get_last_agent_trace(session_id)]
    assert agents == ["planner", "safety", "executor", "tool", "critic", "coordinator"]
