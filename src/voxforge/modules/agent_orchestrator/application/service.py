from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from voxforge.config import Settings
from voxforge.core.domain.entities import Message, MessageRole
from voxforge.core.domain.events import TokenEvent
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.observability.telemetry import get_tracer
from voxforge.modules.agent_orchestrator.application.graph import build_agent_graph

logger = get_logger(__name__)
_tracer = get_tracer(__name__)


@dataclass
class _ChatMessage:
    role: MessageRole
    content: str


class AgentOrchestrator:
    """LangGraph multi-agent orchestrator (planner, safety, executor, critic, coordinator)."""

    def __init__(
        self,
        settings: Settings,
        memory_service: Any | None = None,
        tool_router: Any | None = None,
        knowledge_context_builder: Any | None = None,
        llm: Any | None = None,
    ) -> None:
        self._settings = settings
        self._tool_router = tool_router
        self._llm = llm
        if settings.llm_provider.lower() == "mock":
            from voxforge.modules.agent_orchestrator.application.graph import (
                build_mock_agent_graph,
            )

            self._graph = build_mock_agent_graph(settings, tool_router, llm)
        else:
            self._graph = build_agent_graph(settings, tool_router)
        self._history: dict[UUID, list[_ChatMessage]] = {}
        self._traces: dict[UUID, list[dict]] = {}
        self._memory = memory_service
        self._knowledge_context = knowledge_context_builder
        self._org_ids: dict[UUID, UUID | None] = {}
        self._caller_scopes: dict[UUID, list[str]] = {}
        self._session_prompts: dict[UUID, str] = {}

    def set_session_org(self, session_id: UUID, org_id: UUID | None) -> None:
        self._org_ids[session_id] = org_id

    def set_caller_scopes(self, session_id: UUID, scopes: list[str]) -> None:
        self._caller_scopes[session_id] = list(scopes)

    def set_session_system_prompt(self, session_id: UUID, prompt: str) -> None:
        self._session_prompts[session_id] = prompt

    def _system_prompt_for(self, session_id: UUID) -> str:
        return self._session_prompts.get(session_id, self._settings.system_prompt)

    def init_session(self, session_id: UUID) -> None:
        self._history[session_id] = [
            _ChatMessage(role=MessageRole.SYSTEM, content=self._system_prompt_for(session_id))
        ]
        self._traces[session_id] = []

    def add_user_message(self, session_id: UUID, content: str) -> None:
        if session_id not in self._history:
            self.init_session(session_id)
        self._history[session_id].append(_ChatMessage(role=MessageRole.USER, content=content))

    def add_assistant_message(self, session_id: UUID, content: str) -> None:
        if session_id not in self._history:
            self.init_session(session_id)
        self._history[session_id].append(_ChatMessage(role=MessageRole.ASSISTANT, content=content))

    def load_history(self, session_id: UUID, messages: list[Message]) -> None:
        self._history[session_id] = [
            _ChatMessage(role=MessageRole.SYSTEM, content=self._system_prompt_for(session_id))
        ]
        for msg in messages:
            self._history[session_id].append(_ChatMessage(role=msg.role, content=msg.content))

    async def generate_response(
        self,
        session_id: UUID,
        *,
        model: str | None = None,
        on_agent_step: Callable[[str, str, dict], Any] | None = None,
    ) -> AsyncIterator[TokenEvent]:
        history = self._history.get(session_id, [])
        user_input = _last_user_message(history)

        org_id = self._org_ids.get(session_id)
        if self._memory:
            from voxforge.modules.memory.application.context_builder import ChatMessageLike

            built = await self._memory.build_messages_for_llm(
                org_id=org_id,
                session_id=session_id,
                system_prompt=self._system_prompt_for(session_id),
                recent_messages=[ChatMessageLike(role=m.role, content=m.content) for m in history],
                query=user_input,
            )
            history = [_ChatMessage(role=m.role, content=m.content) for m in built]

        if self._knowledge_context and self._settings.knowledge_context_enabled:
            from voxforge.modules.memory.application.context_builder import ChatMessageLike

            enriched = await self._knowledge_context.enrich_messages(
                [ChatMessageLike(role=m.role, content=m.content) for m in history],
                org_id=org_id,
                query=user_input,
            )
            history = [_ChatMessage(role=m.role, content=m.content) for m in enriched]

        messages = [{"role": m.role.value, "content": m.content} for m in history]

        with _tracer.start_as_current_span("agent_orchestrator.generate") as span:
            span.set_attribute("voxforge.session_id", str(session_id))
            org_id = self._org_ids.get(session_id)
            if org_id is not None:
                span.set_attribute("voxforge.org_id", str(org_id))
            logger.info(
                "agent_orchestrator_run",
                session_id=str(session_id),
                org_id=str(org_id) if org_id else None,
            )
            result = await self._graph.ainvoke(
                {
                    "messages": messages,
                    "user_input": user_input,
                    "plan": "",
                    "draft_response": "",
                    "safety_passed": True,
                    "safety_reason": "",
                    "critic_approved": False,
                    "critic_feedback": "",
                    "final_response": "",
                    "iteration": 0,
                    "session_id": str(session_id),
                    "org_id": str(org_id) if org_id else None,
                    "caller_scopes": self._caller_scopes.get(session_id, []),
                    "agent_trace": [],
                    "tool_calls": [],
                }
            )

        trace = result.get("agent_trace", [])
        self._traces[session_id] = trace

        if on_agent_step:
            for step in trace:
                await _maybe_await(
                    on_agent_step(step["agent"], step["status"], {"summary": step["summary"]})
                )

        final = result.get("final_response") or result.get("draft_response", "")
        if not final:
            final = "I'm sorry, I couldn't generate a response."

        for word in final.split():
            yield TokenEvent(text=word + " ", is_final=False)
        yield TokenEvent(text="", is_final=True)

    def clear_session(self, session_id: UUID) -> None:
        self._history.pop(session_id, None)
        self._traces.pop(session_id, None)
        self._org_ids.pop(session_id, None)
        self._caller_scopes.pop(session_id, None)
        self._session_prompts.pop(session_id, None)

    def get_last_agent_trace(self, session_id: UUID) -> list[dict]:
        return self._traces.get(session_id, [])


async def _maybe_await(result: Any) -> None:
    import asyncio

    if asyncio.iscoroutine(result):
        await result


def _last_user_message(history: list[_ChatMessage]) -> str:
    for msg in reversed(history):
        if msg.role == MessageRole.USER:
            return msg.content
    return ""
