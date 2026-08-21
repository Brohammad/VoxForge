"""LiveKit agent worker — transport adapter into VoicePipelineService."""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker

from voxforge.config import get_settings
from voxforge.core.events.bus import get_event_bus
from voxforge.infrastructure.db.session import get_engine, init_db
from voxforge.infrastructure.livekit.audio_bridge import PIPELINE_SAMPLE_RATE
from voxforge.infrastructure.livekit.audio_publisher import (
    PUBLISH_SAMPLE_RATE,
    LiveKitAudioPublisher,
)
from voxforge.infrastructure.livekit.room_utils import parse_session_id
from voxforge.infrastructure.observability.logging import get_logger, setup_logging
from voxforge.infrastructure.observability.metrics import livekit_room_lifecycle_total
from voxforge.infrastructure.observability.telemetry import get_tracer, setup_telemetry
from voxforge.infrastructure.redis.client import get_redis, init_redis
from voxforge.infrastructure.redis.session_state import RedisSessionStateStore
from voxforge.infrastructure.tools.mcp_runtime_registry import MCPRuntimeRegistry
from voxforge.modules.livekit_gateway.application.session_runner import LiveKitSessionRunner
from voxforge.modules.voice_gateway.application.pipeline_factory import build_voice_pipeline_bundle

logger = get_logger(__name__)
_tracer = get_tracer(__name__)
_infra_ready = False


async def _ensure_infra() -> None:
    global _infra_ready
    if _infra_ready:
        return
    settings = get_settings()
    await init_db(settings.database_url)
    await init_redis(settings.redis_url)
    _infra_ready = True


async def _build_mcp_registry(settings) -> MCPRuntimeRegistry | None:
    if not settings.tools_enabled or not settings.mcp_servers_config.strip():
        return None
    registry = MCPRuntimeRegistry(settings)
    if settings.mcp_startup_discover:
        await registry.discover_all()
    return registry


async def _iter_participant_audio(track) -> asyncio.AsyncIterator:
    from livekit import rtc

    stream = rtc.AudioStream(track, sample_rate=PIPELINE_SAMPLE_RATE, num_channels=1)
    async for event in stream:
        yield event.frame


async def _wait_for_audio_track(participant, timeout: float = 30.0):
    from livekit import rtc

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        for pub in participant.track_publications.values():
            track = pub.track
            if track and track.kind == rtc.TrackKind.KIND_AUDIO:
                return track
        await asyncio.sleep(0.1)
    return None


async def entrypoint(ctx) -> None:
    from livekit.agents import AutoSubscribe

    await _ensure_infra()
    settings = get_settings()
    room_name = ctx.room.name

    with _tracer.start_as_current_span("livekit.room.join") as span:
        span.set_attribute("livekit.room_name", room_name)
        try:
            session_id = parse_session_id(room_name)
        except ValueError as exc:
            livekit_room_lifecycle_total.labels(event="invalid_room").inc()
            logger.error("livekit_invalid_room", room=room_name, error=str(exc))
            return
        span.set_attribute("voxforge.session_id", str(session_id))

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    engine = get_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = get_redis()
    state_store = RedisSessionStateStore(redis, ttl_seconds=settings.session_state_ttl_seconds)
    event_bus = get_event_bus()
    mcp_registry = await _build_mcp_registry(settings)

    runner: LiveKitSessionRunner | None = None
    published_track = None
    shutdown_event = asyncio.Event()

    async def _request_shutdown(_reason: str = "") -> None:
        shutdown_event.set()

    ctx.add_shutdown_callback(_request_shutdown)

    try:
        async with session_factory() as db_session:
            bundle = build_voice_pipeline_bundle(
                db_session,
                state_store,
                event_bus,
                settings,
                mcp_registry=mcp_registry,
            )
            config = await bundle.session_manager.get_session_config(session_id)
            session = await bundle.session_manager.get_session(session_id)
            org_id = session.org_id
            if org_id is not None:
                await bundle.bootstrap_session_agent_config(org_id, session_id)

            from livekit import rtc

            # Mic ingress stays at 16 kHz for STT; agent TTS publishes at 48 kHz (WebRTC).
            audio_source = rtc.AudioSource(PUBLISH_SAMPLE_RATE, 1, queue_size_ms=5000)
            local_track = rtc.LocalAudioTrack.create_audio_track(
                "voxforge-agent",
                audio_source,
            )
            published_track = await ctx.room.local_participant.publish_track(
                local_track,
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
            )
            # Do NOT wait_for_subscription here — that deadlocks before the browser
            # joins. Playout subscription happens after the participant connects.

            publisher = LiveKitAudioPublisher(
                audio_source,
                sample_rate=PUBLISH_SAMPLE_RATE,
                # Client page plays via /demo/hear (avoids double Mac playback).
                mirror_afplay=False,
            )
            runner = LiveKitSessionRunner(
                session_id=session_id,
                session_manager=bundle.session_manager,
                pipeline=bundle.pipeline,
                response_generator=bundle.response_generator,
                settings=settings,
                audio_publisher=publisher,
                org_id=org_id,
                language=config.get("language"),
            )

            async def send_data(payload: dict) -> None:
                await LiveKitSessionRunner.send_json_data(
                    ctx.room.local_participant.publish_data,
                    payload,
                )

            runner.set_data_sender(send_data)
            await runner.prepare(resume=False)

            participant = await ctx.wait_for_participant()
            await runner.handle_participant_connected(participant.identity)

            audio_track = await _wait_for_audio_track(participant)
            if audio_track is None:
                livekit_room_lifecycle_total.labels(event="no_audio_track").inc()
                logger.error("livekit_no_audio_track", session_id=str(session_id))
                return

            @ctx.room.on("data_received")
            def _on_data(data_packet) -> None:
                try:
                    raw = data_packet.data
                    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
                    import json

                    payload = json.loads(text)
                except Exception:
                    return
                if payload.get("type") == "interrupt":
                    asyncio.create_task(runner.handle_client_interrupt())

            @ctx.room.on("participant_disconnected")
            def _on_disconnect(participant_obj) -> None:
                if participant_obj.identity == participant.identity:
                    asyncio.create_task(
                        runner.handle_participant_disconnected(
                            participant.identity,
                            reason="participant_left",
                        )
                    )
                    asyncio.create_task(_delayed_shutdown(shutdown_event, settings))

            @ctx.room.on("participant_connected")
            def _on_reconnect(participant_obj) -> None:
                if participant_obj.identity == participant.identity:
                    asyncio.create_task(runner.handle_reconnect())

            await runner.start(_iter_participant_audio(audio_track))
            await shutdown_event.wait()
    except Exception as exc:
        livekit_room_lifecycle_total.labels(event="worker_error").inc()
        logger.exception("livekit_worker_error", session_id=str(session_id), error=str(exc))
        raise
    finally:
        if runner is not None:
            await runner.shutdown(reason="worker_exit")
        if published_track is not None:
            try:
                await ctx.room.local_participant.unpublish_track(published_track.sid)
            except Exception:
                pass


async def _delayed_shutdown(shutdown_event: asyncio.Event, settings) -> None:
    await asyncio.sleep(settings.livekit_reconnect_grace_seconds)
    shutdown_event.set()


def main() -> None:
    from livekit.agents import WorkerOptions, cli

    settings = get_settings()
    setup_logging(settings.log_level)
    setup_telemetry(settings)

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name=settings.livekit_agent_name,
            ws_url=settings.livekit_url or None,
            api_key=settings.livekit_api_key or None,
            api_secret=settings.livekit_api_secret or None,
        )
    )


if __name__ == "__main__":
    main()
