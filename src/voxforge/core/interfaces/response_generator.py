from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol
from uuid import UUID

from voxforge.core.domain.entities import Message
from voxforge.core.domain.events import TokenEvent


class ResponseGenerator(Protocol):
    def init_session(self, session_id: UUID) -> None: ...

    def add_user_message(self, session_id: UUID, content: str) -> None: ...

    def add_assistant_message(self, session_id: UUID, content: str) -> None: ...

    def load_history(self, session_id: UUID, messages: list[Message]) -> None: ...

    def set_session_org(self, session_id: UUID, org_id: UUID | None) -> None: ...

    def generate_response(
        self,
        session_id: UUID,
        *,
        model: str | None = None,
        on_agent_step: Callable[[str, str, dict], Any] | None = None,
    ) -> AsyncIterator[TokenEvent]: ...

    def clear_session(self, session_id: UUID) -> None: ...

    def get_last_agent_trace(self, session_id: UUID) -> list[dict]: ...
