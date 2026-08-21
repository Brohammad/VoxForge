import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import async_sessionmaker

from voxforge.api.ws.auth import resolve_ws_principal
from voxforge.config import get_settings
from voxforge.core.domain.auth import effective_scopes
from voxforge.core.domain.entities import TransportType
from voxforge.core.domain.events import AudioChunk, TranscriptEvent
from voxforge.core.events.bus import get_event_bus
from voxforge.core.exceptions import ForbiddenError, SessionNotFoundError, UnauthorizedError
from voxforge.infrastructure.db.session import get_engine
from voxforge.infrastructure.http.rate_limit import (
    enforce_authenticated_limits,
    enforce_ws_connect_limit,
)
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.observability.metrics import active_sessions, ws_connections
from voxforge.infrastructure.redis.client import get_redis
from voxforge.infrastructure.redis.session_state import RedisSessionStateStore
from voxforge.infrastructure.tools.mcp_runtime_registry import MCPRuntimeRegistry
from voxforge.modules.auth.application.service import AuthService
from voxforge.modules.session_manager.application.service import SessionManager
from voxforge.modules.voice_gateway.application.pipeline import (
    PipelineCallbacks,
    VoicePipelineService,
)
from voxforge.modules.voice_gateway.application.pipeline_factory import build_voice_pipeline_bundle

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/api/v1/ws/voice")
async def voice_websocket(websocket: WebSocket) -> None:
    settings = get_settings()
    connect_result = await enforce_ws_connect_limit(websocket, settings=settings)
    if not connect_result.allowed:
        reason = (
            "Rate limiting unavailable" if connect_result.redis_error else "Rate limit exceeded"
        )
        await websocket.close(code=1008, reason=reason)
        return

    await websocket.accept()
    ws_connections.inc()
    settings = get_settings()

    session_id: UUID | None = None
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    listening_task: asyncio.Task | None = None
    heartbeat_task: asyncio.Task | None = None

    engine = get_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as db_session:
            state_store = RedisSessionStateStore(
                get_redis(), ttl_seconds=settings.session_state_ttl_seconds
            )
            event_bus = get_event_bus()
            auth_service = AuthService(db_session, settings)
            mcp_registry: MCPRuntimeRegistry | None = getattr(
                websocket.app.state, "mcp_registry", None
            )
            bundle = build_voice_pipeline_bundle(
                db_session,
                state_store,
                event_bus,
                settings,
                mcp_registry=mcp_registry,
            )
            session_manager = bundle.session_manager
            pipeline = bundle.pipeline
            response_generator = bundle.response_generator

            while True:
                message = await websocket.receive()

                if message.get("type") == "websocket.disconnect":
                    break

                if "text" in message:
                    result = await _handle_control_message(
                        message["text"],
                        websocket=websocket,
                        session_manager=session_manager,
                        auth_service=auth_service,
                        bundle=bundle,
                        response_generator=response_generator,
                        pipeline=pipeline,
                        audio_queue=audio_queue,
                        session_id=session_id,
                        listening_task=listening_task,
                        heartbeat_task=heartbeat_task,
                        settings=settings,
                    )
                    session_id = result.get("session_id", session_id)
                    if result.get("response_generator") is not None:
                        response_generator = result["response_generator"]
                    if result.get("listening_task"):
                        listening_task = result["listening_task"]
                    if result.get("heartbeat_task"):
                        heartbeat_task = result["heartbeat_task"]
                    if result.get("session_id") is None and session_id is not None:
                        session_id = None

                elif "bytes" in message and session_id is not None:
                    await audio_queue.put(message["bytes"])

    except WebSocketDisconnect:
        logger.info("ws_disconnected", session_id=str(session_id))
    except Exception as exc:
        logger.error("ws_error", session_id=str(session_id), error=str(exc))
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "internal_error",
                    "message": "Internal error",
                }
            )
        except Exception:
            pass
    finally:
        ws_connections.dec()
        if listening_task and not listening_task.done():
            listening_task.cancel()
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()
        await audio_queue.put(None)
        if session_id is not None:
            active_sessions.dec()
            try:
                async with session_factory() as db_session:
                    state_store = RedisSessionStateStore(
                        get_redis(), ttl_seconds=settings.session_state_ttl_seconds
                    )
                    sm = SessionManager(db_session, state_store, get_event_bus(), settings)
                    await sm.end_session(session_id, reason="disconnect")
                    await db_session.commit()
            except Exception as exc:
                logger.warning(
                    "ws_disconnect_cleanup_failed",
                    session_id=str(session_id),
                    error=str(exc),
                )


async def _handle_control_message(
    raw: str,
    *,
    websocket: WebSocket,
    session_manager: SessionManager,
    auth_service: AuthService,
    bundle,
    response_generator,
    pipeline: VoicePipelineService,
    audio_queue: asyncio.Queue,
    session_id: UUID | None,
    listening_task: asyncio.Task | None,
    heartbeat_task: asyncio.Task | None,
    settings,
) -> dict:
    result: dict = {}

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await websocket.send_json(
            {"type": "error", "code": "invalid_json", "message": "Invalid JSON"}
        )
        return result

    msg_type = msg.get("type")

    if msg_type == "start":
        config = msg.get("config", {})
        resume_id = msg.get("session_id")

        try:
            principal = await resolve_ws_principal(websocket, auth_service, settings, msg)
        except (UnauthorizedError, ForbiddenError) as exc:
            await websocket.send_json({"type": "error", "code": exc.code, "message": exc.message})
            return result

        try:
            await enforce_authenticated_limits(
                path="/api/v1/ws/voice",
                settings=settings,
                category="voice_ws",
                org_id=str(principal.org_id),
                user_id=str(principal.user_id) if principal.user_id else None,
                api_key_id=str(principal.api_key_id) if principal.api_key_id else None,
            )
        except HTTPException as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "rate_limit_exceeded",
                    "message": exc.detail,
                }
            )
            return result

        if resume_id:
            try:
                session = await session_manager.get_session(
                    UUID(resume_id), org_id=principal.org_id
                )
                session = await session_manager.resume_session(
                    UUID(resume_id), msg.get("last_sequence", 0)
                )
                response_generator.set_caller_scopes(session.id, effective_scopes(principal))
            except SessionNotFoundError:
                await websocket.send_json(
                    {"type": "error", "code": "session_not_found", "message": "Session not found"}
                )
                return result
        else:
            config = {
                **config,
                "caller_scopes": effective_scopes(principal),
            }
            session = await session_manager.create_session(
                transport_type=TransportType.WEBSOCKET,
                config=config,
                org_id=principal.org_id,
                created_by_user_id=principal.user_id,
            )

        session = await session_manager.activate_session(session.id)
        await session_manager.commit()

        import structlog

        structlog.contextvars.bind_contextvars(
            session_id=str(session.id),
            org_id=str(principal.org_id),
        )

        response_generator = await bundle.bootstrap_session_agent_config(
            principal.org_id, session.id
        )
        result["response_generator"] = response_generator

        response_generator.init_session(session.id)
        response_generator.set_session_org(session.id, principal.org_id)
        response_generator.set_caller_scopes(session.id, effective_scopes(principal))
        pipeline.set_session_org(session.id, principal.org_id)
        messages = await session_manager.get_messages(session.id)
        if messages:
            response_generator.load_history(session.id, messages)

        result["session_id"] = session.id
        active_sessions.inc()

        callbacks = _build_callbacks(websocket)
        sid = session.id

        async def listen():
            await pipeline.run_listening(
                sid,
                audio_queue,
                callbacks,
                language=config.get("language"),
            )

        result["listening_task"] = asyncio.create_task(listen())

        async def heartbeat_loop():
            while True:
                await asyncio.sleep(settings.session_heartbeat_interval_seconds)
                await session_manager.record_heartbeat(sid)

        result["heartbeat_task"] = asyncio.create_task(heartbeat_loop())

        await websocket.send_json({"type": "started", "session_id": str(session.id)})

    elif msg_type == "interrupt":
        if session_id:
            await pipeline.interrupt(session_id)
            await websocket.send_json({"type": "interrupted"})

    elif msg_type == "end":
        if session_id:
            await audio_queue.put(None)
            if listening_task and not listening_task.done():
                listening_task.cancel()
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
            await session_manager.end_session(session_id)
            await session_manager.commit()
            response_generator.clear_session(session_id)
            active_sessions.dec()
            result["session_id"] = None
            await websocket.send_json({"type": "ended", "session_id": str(session_id)})

    elif msg_type == "ping":
        if session_id:
            await session_manager.record_heartbeat(session_id)
        await websocket.send_json({"type": "pong"})

    return result


def _build_callbacks(websocket: WebSocket) -> PipelineCallbacks:
    async def on_transcript(event: TranscriptEvent) -> None:
        await websocket.send_json(
            {
                "type": "transcript",
                "partial": event.is_partial,
                "text": event.text,
                "confidence": event.confidence,
                "language": event.language,
            }
        )

    async def on_token(text: str) -> None:
        await websocket.send_json({"type": "response", "token": text})

    async def on_audio(chunk: AudioChunk) -> None:
        await websocket.send_bytes(chunk.data)

    async def on_metrics(metrics) -> None:
        await websocket.send_json(
            {
                "type": "metric",
                "stt_ms": metrics.stt_ms,
                "llm_first_token_ms": metrics.llm_first_token_ms,
                "tts_first_byte_ms": metrics.tts_first_byte_ms,
                "e2e_ms": metrics.e2e_ms,
            }
        )

    async def on_error(code: str, message: str) -> None:
        await websocket.send_json({"type": "error", "code": code, "message": message})

    async def on_agent_step(agent: str, status: str, payload: dict) -> None:
        await websocket.send_json(
            {
                "type": "agent_step",
                "agent": agent,
                "status": status,
                **payload,
            }
        )

    return PipelineCallbacks(
        on_transcript=on_transcript,
        on_token=on_token,
        on_audio=on_audio,
        on_metrics=on_metrics,
        on_error=on_error,
        on_agent_step=on_agent_step,
    )
