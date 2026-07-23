from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from voxforge.api.dependencies import (
    get_livekit_service,
    get_session_manager,
    rate_limit_category,
    require_scope,
)
from voxforge.api.ws.livekit_proxy import browser_livekit_url
from voxforge.config import Settings, get_settings
from voxforge.core.domain.auth import Principal
from voxforge.core.exceptions import ProviderError, SessionNotFoundError
from voxforge.infrastructure.livekit.dispatch_service import LiveKitDispatchService
from voxforge.infrastructure.livekit.token_service import LiveKitTokenService
from voxforge.modules.session_manager.application.service import SessionManager

router = APIRouter(prefix="/livekit", tags=["livekit"])


class LiveKitTokenRequest(BaseModel):
    participant_identity: str = Field(..., min_length=1, max_length=128)
    participant_name: str | None = Field(default=None, max_length=128)


class LiveKitTokenResponse(BaseModel):
    token: str
    room_name: str
    livekit_url: str
    session_id: UUID


@router.post("/sessions/{session_id}/token", response_model=LiveKitTokenResponse)
async def create_livekit_token(
    session_id: UUID,
    body: LiveKitTokenRequest,
    request: Request,
    _: None = Depends(rate_limit_category("livekit")),
    principal: Principal = Depends(require_scope("sessions:write")),
    session_manager: SessionManager = Depends(get_session_manager),
    livekit: LiveKitTokenService = Depends(get_livekit_service),
    settings: Settings = Depends(get_settings),
) -> LiveKitTokenResponse:
    if not livekit.enabled:
        raise HTTPException(status_code=503, detail="LiveKit is not configured")

    try:
        await session_manager.get_session(session_id, org_id=principal.org_id)
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found") from None

    try:
        result = livekit.create_participant_token(
            session_id=session_id,
            participant_identity=body.participant_identity,
            participant_name=body.participant_name,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=exc.message) from exc

    dispatch = LiveKitDispatchService(settings)
    await dispatch.dispatch_agent(result["room_name"])

    # Browser clients use same-origin /lk proxy when LiveKit is local Docker.
    result = {**result, "livekit_url": browser_livekit_url(request)}
    return LiveKitTokenResponse(session_id=session_id, **result)
