from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.config import Settings
from voxforge.core.domain.entities import (
    MessageRole,
    SessionPhase,
    SessionState,
    SessionStatus,
    TransportType,
    TurnMetrics,
    VoiceSession,
)
from voxforge.core.domain.events import SessionCreated, SessionEnded, SessionResumed
from voxforge.core.events.bus import EventBus
from voxforge.core.exceptions import SessionStateError
from voxforge.infrastructure.db.repositories import SessionRepository
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.observability.metrics import session_consistency_total
from voxforge.infrastructure.observability.telemetry import get_tracer
from voxforge.infrastructure.redis.session_state import RedisSessionStateStore

logger = get_logger(__name__)
_tracer = get_tracer(__name__)

_TERMINAL_STATUSES = frozenset({SessionStatus.COMPLETED, SessionStatus.FAILED})


def _phase_for_status(status: SessionStatus) -> SessionPhase:
    if status == SessionStatus.HANDOFF_PENDING:
        return SessionPhase.HANDOFF_PENDING
    if status == SessionStatus.HANDOFF_ACTIVE:
        return SessionPhase.HANDOFF_ACTIVE
    if status == SessionStatus.ACTIVE:
        return SessionPhase.LISTENING
    return SessionPhase.IDLE


class SessionManager:
    def __init__(
        self,
        db_session: AsyncSession,
        state_store: RedisSessionStateStore,
        event_bus: EventBus,
        settings: Settings,
    ) -> None:
        self._repo = SessionRepository(db_session)
        self._state_store = state_store
        self._event_bus = event_bus
        self._settings = settings
        self._db_session = db_session

    @property
    def db_session(self) -> AsyncSession:
        return self._db_session

    async def create_session(
        self,
        *,
        transport_type: TransportType = TransportType.WEBSOCKET,
        config: dict | None = None,
        org_id: UUID | None = None,
        created_by_user_id: UUID | None = None,
    ) -> VoiceSession:
        session_config = config or {}
        session = await self._repo.create(
            transport_type=transport_type,
            metadata=session_config,
            org_id=org_id,
            created_by_user_id=created_by_user_id,
        )
        state = SessionState(session_id=session.id, config=session_config)
        try:
            await self._write_ephemeral_state(session.id, state, session.status)
        except Exception as exc:
            logger.error(
                "session_redis_create_failed",
                session_id=str(session.id),
                error=str(exc),
            )
            session_consistency_total.labels(operation="create", outcome="compensated").inc()
            await self._repo.end_session(session.id, status=SessionStatus.FAILED)
            raise SessionStateError("Failed to initialize session ephemeral state") from exc
        session_consistency_total.labels(operation="create", outcome="success").inc()
        await self._event_bus.publish(SessionCreated(session_id=session.id))
        return session

    async def activate_session(self, session_id: UUID) -> VoiceSession:
        session = await self._repo.get(session_id)
        if session.status == SessionStatus.ACTIVE:
            session_consistency_total.labels(operation="activate", outcome="idempotent").inc()
            return session
        if session.status in _TERMINAL_STATUSES:
            raise SessionStateError(f"Cannot activate terminal session {session_id}")
        session = await self._repo.update_status(session_id, SessionStatus.ACTIVE)
        await self._ensure_ephemeral_state(session)
        await self._state_store.update_phase(session_id, SessionPhase.LISTENING)
        session_consistency_total.labels(operation="activate", outcome="success").inc()
        return session

    async def resume_session(self, session_id: UUID, last_sequence: int = 0) -> VoiceSession:
        session = await self._repo.get(session_id)
        if session.status in _TERMINAL_STATUSES:
            raise SessionStateError(f"Cannot resume terminal session {session_id}")
        state = await self._state_store.get_state_or_none(session_id)
        if state is None:
            await self._ensure_ephemeral_state(session)
            state = await self._state_store.get_state(session_id)
        if state.sequence < last_sequence:
            state.sequence = last_sequence
            await self._write_ephemeral_state(session_id, state, session.status)
        await self._state_store.record_heartbeat(session_id)
        await self._event_bus.publish(
            SessionResumed(session_id=session_id, last_sequence=last_sequence)
        )
        return session

    async def end_session(self, session_id: UUID, *, reason: str = "normal") -> VoiceSession:
        session = await self._repo.get(session_id)
        if session.status in _TERMINAL_STATUSES:
            await self._best_effort_delete_redis(session_id)
            session_consistency_total.labels(operation="end", outcome="idempotent").inc()
            return session

        ended = await self._repo.end_session(session_id)
        redis_deleted = await self._best_effort_delete_redis(session_id)
        outcome = "success" if redis_deleted else "redis_cleanup_failed"
        session_consistency_total.labels(operation="end", outcome=outcome).inc()
        await self._event_bus.publish(SessionEnded(session_id=session_id, reason=reason))
        return ended

    async def ensure_ephemeral_state(self, session_id: UUID) -> SessionState:
        """Rebuild Redis session state from PostgreSQL (source of truth)."""
        session = await self._repo.get(session_id)
        return await self._ensure_ephemeral_state(session)

    async def save_user_message(self, session_id: UUID, content: str, metadata: dict | None = None):
        return await self._repo.add_message(
            session_id,
            role=MessageRole.USER,
            content=content,
            provider_metadata=metadata or {},
        )

    async def save_assistant_message(
        self, session_id: UUID, content: str, metadata: dict | None = None
    ):
        return await self._repo.add_message(
            session_id,
            role=MessageRole.ASSISTANT,
            content=content,
            provider_metadata=metadata or {},
        )

    async def save_system_message(self, session_id: UUID, content: str):
        return await self._repo.add_message(
            session_id,
            role=MessageRole.SYSTEM,
            content=content,
        )

    async def get_messages(self, session_id: UUID, offset: int = 0, limit: int = 50):
        return await self._repo.get_messages(session_id, offset=offset, limit=limit)

    async def save_turn_metrics(self, session_id: UUID, metrics: TurnMetrics) -> None:
        if metrics.stt_ms is not None:
            await self._repo.add_metric(session_id, metric_name="stt_ms", value_ms=metrics.stt_ms)
        if metrics.llm_first_token_ms is not None:
            await self._repo.add_metric(
                session_id, metric_name="llm_first_token_ms", value_ms=metrics.llm_first_token_ms
            )
        if metrics.tts_first_byte_ms is not None:
            await self._repo.add_metric(
                session_id, metric_name="tts_first_byte_ms", value_ms=metrics.tts_first_byte_ms
            )
        if metrics.e2e_ms is not None:
            await self._repo.add_metric(session_id, metric_name="e2e_ms", value_ms=metrics.e2e_ms)

    async def get_session(self, session_id: UUID, *, org_id: UUID | None = None) -> VoiceSession:
        return await self._repo.get(session_id, org_id=org_id)

    async def set_interrupt(self, session_id: UUID) -> SessionState:
        return await self._state_store.set_interrupt(session_id, True)

    async def clear_interrupt(self, session_id: UUID) -> SessionState:
        return await self._state_store.clear_interrupt(session_id)

    async def update_phase(self, session_id: UUID, phase: SessionPhase) -> SessionState:
        return await self._state_store.update_phase(session_id, phase)

    async def record_heartbeat(self, session_id: UUID) -> None:
        await self._state_store.record_heartbeat(session_id)

    async def is_stale(self, session_id: UUID) -> bool:
        return await self._state_store.is_stale(
            session_id, self._settings.session_stale_timeout_seconds
        )

    async def get_session_config(self, session_id: UUID) -> dict:
        state = await self._state_store.get_state_or_none(session_id)
        if state is not None:
            return state.config
        session = await self._repo.get(session_id)
        return dict(session.metadata)

    async def get_session_phase(self, session_id: UUID) -> SessionPhase:
        state = await self._state_store.get_state_or_none(session_id)
        if state is not None:
            return state.phase
        session = await self._repo.get(session_id)
        return _phase_for_status(session.status)

    async def commit(self) -> None:
        await self._db_session.commit()

    async def apply_handoff_pending(
        self,
        session_id: UUID,
        *,
        handoff_id: UUID,
        handoff_context: dict,
    ) -> None:
        await self._repo.update_status(session_id, SessionStatus.HANDOFF_PENDING)
        state = await self._load_or_reconcile_state(session_id)
        state.phase = SessionPhase.HANDOFF_PENDING
        state.config = {
            **state.config,
            "handoff": handoff_context,
            "consecutive_tool_failures": state.config.get("consecutive_tool_failures", 0),
        }
        await self._write_ephemeral_state(
            session_id,
            state,
            SessionStatus.HANDOFF_PENDING,
        )

    async def apply_handoff_active(self, session_id: UUID, *, handoff_id: UUID) -> None:
        await self._repo.update_status(session_id, SessionStatus.HANDOFF_ACTIVE)
        state = await self._load_or_reconcile_state(session_id)
        state.phase = SessionPhase.HANDOFF_ACTIVE
        handoff_cfg = state.config.get("handoff", {})
        if isinstance(handoff_cfg, dict):
            handoff_cfg["handoff_id"] = str(handoff_id)
            state.config["handoff"] = handoff_cfg
        await self._write_ephemeral_state(
            session_id,
            state,
            SessionStatus.HANDOFF_ACTIVE,
        )

    async def clear_handoff(self, session_id: UUID) -> None:
        await self._repo.update_status(session_id, SessionStatus.ACTIVE)
        state = await self._load_or_reconcile_state(session_id)
        state.phase = SessionPhase.LISTENING
        state.config.pop("handoff", None)
        await self._write_ephemeral_state(session_id, state, SessionStatus.ACTIVE)

    async def track_tool_failures(self, session_id: UUID, failed_count: int) -> int:
        state = await self._load_or_reconcile_state(session_id)
        current = int(state.config.get("consecutive_tool_failures", 0))
        if failed_count > 0:
            current += failed_count
        else:
            current = 0
        state.config["consecutive_tool_failures"] = current
        await self._write_ephemeral_state(
            session_id,
            state,
            (await self._repo.get(session_id)).status,
        )
        return current

    async def _ensure_ephemeral_state(self, session: VoiceSession) -> SessionState:
        with _tracer.start_as_current_span("session.reconcile_ephemeral") as span:
            span.set_attribute("voxforge.session_id", str(session.id))
            existing = await self._state_store.get_state_or_none(session.id)
            if existing is not None:
                return existing
            if session.status in _TERMINAL_STATUSES:
                raise SessionStateError(
                    f"Cannot reconcile ephemeral state for terminal session {session.id}"
                )
            state = SessionState(
                session_id=session.id,
                phase=_phase_for_status(session.status),
                config=dict(session.metadata),
            )
            await self._write_ephemeral_state(session.id, state, session.status)
            logger.info(
                "session_ephemeral_reconciled",
                session_id=str(session.id),
                status=session.status.value,
            )
            session_consistency_total.labels(operation="reconcile", outcome="success").inc()
            return state

    async def _load_or_reconcile_state(self, session_id: UUID) -> SessionState:
        state = await self._state_store.get_state_or_none(session_id)
        if state is not None:
            return state
        session = await self._repo.get(session_id)
        return await self._ensure_ephemeral_state(session)

    async def _write_ephemeral_state(
        self,
        session_id: UUID,
        state: SessionState,
        status: SessionStatus,
    ) -> None:
        ttl = self._ttl_for_status(status)
        await self._state_store.save_state(state, ttl_seconds=ttl)
        await self._state_store.record_heartbeat(session_id)

    def _ttl_for_status(self, status: SessionStatus) -> int:
        if status in (SessionStatus.HANDOFF_PENDING, SessionStatus.HANDOFF_ACTIVE):
            return self._settings.handoff_session_ttl_seconds
        return self._settings.session_state_ttl_seconds

    async def _best_effort_delete_redis(self, session_id: UUID) -> bool:
        try:
            await self._state_store.delete_state(session_id)
            return True
        except Exception as exc:
            logger.warning(
                "session_redis_delete_failed",
                session_id=str(session_id),
                error=str(exc),
            )
            return False
