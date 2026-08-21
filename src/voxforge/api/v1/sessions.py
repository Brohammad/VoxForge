from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.api.dependencies import (
    get_handoff_orchestrator,
    get_session_manager,
    rate_limit_category,
    require_scope,
)
from voxforge.config import get_settings
from voxforge.core.domain.auth import Principal
from voxforge.core.domain.entities import SessionStatus, TransportType, VoiceSession
from voxforge.core.domain.handoff import HandoffTrigger
from voxforge.core.exceptions import SessionNotFoundError
from voxforge.infrastructure.db.session import get_db_session
from voxforge.modules.handoff.application.orchestrator import HandoffOrchestrator
from voxforge.modules.handoff.application.policy_loader import load_escalation_policy
from voxforge.modules.session_manager.application.service import SessionManager

router = APIRouter(prefix="/sessions", tags=["sessions"])

# Client-supplied session config must stay small and schema-bound (no free-form JSON bags).
_MAX_SESSION_CONFIG_BYTES = 4096


class SessionConfig(BaseModel):
    """Allowlisted session options passed at create time."""

    model_config = ConfigDict(extra="forbid")

    language: str | None = Field(default=None, max_length=16)
    voice_id: str | None = Field(default=None, max_length=128)

    @field_validator("language", "voice_id")
    @classmethod
    def strip_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class CreateSessionRequest(BaseModel):
    transport_type: TransportType = TransportType.WEBSOCKET
    config: SessionConfig = Field(default_factory=SessionConfig)

    def config_dict(self) -> dict:
        data = self.config.model_dump(exclude_none=True)
        encoded = self.config.model_dump_json(exclude_none=True)
        if len(encoded.encode("utf-8")) > _MAX_SESSION_CONFIG_BYTES:
            raise ValueError(f"session config exceeds {_MAX_SESSION_CONFIG_BYTES} bytes")
        return data


class CreateSessionResponse(BaseModel):
    session_id: UUID
    transport_type: TransportType
    ws_url: str | None = None
    livekit_url: str | None = None
    status: SessionStatus


class SessionResponse(BaseModel):
    id: UUID
    status: SessionStatus
    transport_type: TransportType
    org_id: UUID | None = None
    metadata: dict
    started_at: str
    ended_at: str | None = None
    total_latency_ms: float | None = None

    @classmethod
    def from_entity(cls, session: VoiceSession) -> "SessionResponse":
        return cls(
            id=session.id,
            status=session.status,
            transport_type=session.transport_type,
            org_id=session.org_id,
            metadata=session.metadata,
            started_at=session.started_at.isoformat(),
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
            total_latency_ms=session.total_latency_ms,
        )


class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    content_type: str
    created_at: str


class MessagesListResponse(BaseModel):
    messages: list[MessageResponse]
    offset: int
    limit: int


@router.post("", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    principal: Principal = Depends(require_scope("sessions:write")),
    _: None = Depends(rate_limit_category("sessions_create")),
    session_manager: SessionManager = Depends(get_session_manager),
    db: AsyncSession = Depends(get_db_session),
) -> CreateSessionResponse:
    session = await session_manager.create_session(
        transport_type=body.transport_type,
        config=body.config_dict(),
        org_id=principal.org_id,
        created_by_user_id=principal.user_id,
    )
    await session_manager.commit()
    settings = get_settings()
    ws_url = "/api/v1/ws/voice" if body.transport_type == TransportType.WEBSOCKET else None
    livekit_url = (
        settings.livekit_url
        if body.transport_type == TransportType.WEBRTC and settings.livekit_url
        else None
    )
    return CreateSessionResponse(
        session_id=session.id,
        transport_type=body.transport_type,
        ws_url=ws_url,
        livekit_url=livekit_url,
        status=session.status,
    )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    principal: Principal = Depends(require_scope("sessions:read")),
    session_manager: SessionManager = Depends(get_session_manager),
) -> SessionResponse:
    try:
        session = await session_manager.get_session(session_id, org_id=principal.org_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found") from None
    return SessionResponse.from_entity(session)


class SessionHandoffRequest(BaseModel):
    trigger: HandoffTrigger = HandoffTrigger.USER_REQUEST
    reason: str = ""
    priority: str = "normal"
    customer_email: str | None = None


@router.post("/{session_id}/handoff", status_code=201)
async def initiate_session_handoff(
    session_id: UUID,
    body: SessionHandoffRequest,
    principal: Principal = Depends(require_scope("sessions:write")),
    session_manager: SessionManager = Depends(get_session_manager),
    orchestrator: HandoffOrchestrator = Depends(get_handoff_orchestrator),
    db: AsyncSession = Depends(get_db_session),
):
    from voxforge.api.v1.handoffs import _to_response
    from voxforge.infrastructure.db.handoff_repository import HandoffRepository

    try:
        await session_manager.get_session(session_id, org_id=principal.org_id)
        config = await session_manager.get_session_config(session_id)
        policy = load_escalation_policy(config, get_settings())
        package = await orchestrator.initiate_handoff(
            org_id=principal.org_id,
            session_id=session_id,
            trigger=body.trigger,
            reason=body.reason or f"Handoff triggered via API ({body.trigger.value})",
            policy=policy,
            customer_email=body.customer_email,
            priority=body.priority,
        )
        await session_manager.commit()
        await db.commit()
        record = await HandoffRepository(db).get_handoff(
            package.handoff_id, org_id=principal.org_id
        )
        return _to_response(record)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found") from None


@router.get("/{session_id}/messages", response_model=MessagesListResponse)
async def get_messages(
    session_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(require_scope("sessions:read")),
    session_manager: SessionManager = Depends(get_session_manager),
) -> MessagesListResponse:
    try:
        await session_manager.get_session(session_id, org_id=principal.org_id)
        messages = await session_manager.get_messages(session_id, offset=offset, limit=limit)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found") from None

    return MessagesListResponse(
        messages=[
            MessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role.value,
                content=m.content,
                content_type=m.content_type,
                created_at=m.created_at.isoformat(),
            )
            for m in messages
        ],
        offset=offset,
        limit=limit,
    )


@router.delete("/{session_id}", response_model=SessionResponse)
async def end_session(
    session_id: UUID,
    principal: Principal = Depends(require_scope("sessions:delete")),
    session_manager: SessionManager = Depends(get_session_manager),
    db: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    try:
        await session_manager.get_session(session_id, org_id=principal.org_id)
        session = await session_manager.end_session(session_id)
        await session_manager.commit()
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found") from None
    return SessionResponse.from_entity(session)
