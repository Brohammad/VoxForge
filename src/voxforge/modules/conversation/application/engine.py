from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from voxforge.config import Settings
from voxforge.core.domain.entities import Message, MessageRole
from voxforge.core.domain.events import TokenEvent
from voxforge.core.interfaces.providers import LLMProvider
from voxforge.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _ChatMessage:
    role: MessageRole
    content: str


class ConversationEngine:
    def __init__(
        self,
        llm_provider: LLMProvider,
        settings: Settings,
        memory_service: Any | None = None,
        knowledge_context_builder: Any | None = None,
    ) -> None:
        self._llm = llm_provider
        self._settings = settings
        self._memory = memory_service
        self._knowledge_context = knowledge_context_builder
        self._history: dict[UUID, list[_ChatMessage]] = {}
        self._org_ids: dict[UUID, UUID | None] = {}
        self._session_prompts: dict[UUID, str] = {}

    def set_session_org(self, session_id: UUID, org_id: UUID | None) -> None:
        self._org_ids[session_id] = org_id

    def set_caller_scopes(self, session_id: UUID, scopes: list[str]) -> None:
        return

    def set_session_system_prompt(self, session_id: UUID, prompt: str) -> None:
        self._session_prompts[session_id] = prompt

    def _system_prompt_for(self, session_id: UUID) -> str:
        return self._session_prompts.get(session_id, self._settings.system_prompt)

    def init_session(self, session_id: UUID) -> None:
        self._history[session_id] = [
            _ChatMessage(role=MessageRole.SYSTEM, content=self._system_prompt_for(session_id))
        ]

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
        model = model or self._settings.default_llm_model
        query = _last_user_message(history)

        org_id = self._org_ids.get(session_id)
        if self._memory:
            from voxforge.modules.memory.application.context_builder import ChatMessageLike

            built = await self._memory.build_messages_for_llm(
                org_id=org_id,
                session_id=session_id,
                system_prompt=self._system_prompt_for(session_id),
                recent_messages=[ChatMessageLike(role=m.role, content=m.content) for m in history],
                query=query,
            )
            history = [_ChatMessage(role=m.role, content=m.content) for m in built]

        if self._knowledge_context and self._settings.knowledge_context_enabled:
            from voxforge.modules.memory.application.context_builder import ChatMessageLike

            enriched = await self._knowledge_context.enrich_messages(
                [ChatMessageLike(role=m.role, content=m.content) for m in history],
                org_id=org_id,
                query=query,
            )
            history = [_ChatMessage(role=m.role, content=m.content) for m in enriched]

        logger.info("conversation_generate", session_id=str(session_id), model=model)
        async for event in self._llm.generate_stream(history, model=model):
            yield event

    def clear_session(self, session_id: UUID) -> None:
        self._history.pop(session_id, None)
        self._org_ids.pop(session_id, None)
        self._session_prompts.pop(session_id, None)

    def get_last_agent_trace(self, session_id: UUID) -> list[dict]:
        return []


def _last_user_message(history: list[_ChatMessage]) -> str:
    for msg in reversed(history):
        if msg.role == MessageRole.USER:
            return msg.content
    return ""
