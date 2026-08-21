"""Run VoicePipelineService for a LiveKit room session (transport-only)."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from voxforge.config import Settings
from voxforge.core.domain.entities import SessionPhase, TransportType
from voxforge.core.exceptions import SessionNotFoundError
from voxforge.infrastructure.livekit.audio_bridge import frame_to_pipeline_pcm
from voxforge.infrastructure.livekit.audio_publisher import AudioPublisher
from voxforge.infrastructure.livekit.transport_callbacks import build_livekit_callbacks
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.observability.metrics import (
    active_sessions,
    livekit_barge_in_total,
    livekit_participant_events_total,
    livekit_reconnection_attempts_total,
    livekit_room_lifecycle_total,
    livekit_streaming_latency_seconds,
)
from voxforge.infrastructure.observability.telemetry import get_tracer
from voxforge.modules.session_manager.application.service import SessionManager
from voxforge.modules.voice_gateway.application.pipeline import VoicePipelineService

logger = get_logger(__name__)
_tracer = get_tracer(__name__)


class IncomingAudioFrame(Protocol):
    @property
    def data(self) -> bytes | memoryview: ...

    @property
    def sample_rate(self) -> int: ...

    @property
    def num_channels(self) -> int: ...


@dataclass
class LiveKitSessionRunner:
    """Bridges LiveKit participant audio into ``VoicePipelineService``."""

    session_id: UUID
    session_manager: SessionManager
    pipeline: VoicePipelineService
    response_generator: object
    settings: Settings
    audio_publisher: AudioPublisher
    org_id: UUID | None = None
    language: str | None = None
    _shutdown: asyncio.Event = field(default_factory=asyncio.Event)
    _audio_queue: asyncio.Queue[bytes | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=256)
    )
    _listening_task: asyncio.Task | None = field(default=None, init=False)
    _heartbeat_task: asyncio.Task | None = field(default=None, init=False)
    _ingress_task: asyncio.Task | None = field(default=None, init=False)
    _send_data: Callable[[dict], Awaitable[None]] | None = field(default=None, init=False)

    async def prepare(self, *, resume: bool = False, last_sequence: int = 0) -> None:
        with _tracer.start_as_current_span("livekit.session.prepare") as span:
            span.set_attribute("voxforge.session_id", str(self.session_id))
            span.set_attribute("voxforge.transport", "livekit")
            span.set_attribute("voxforge.resume", resume)
            try:
                if resume:
                    await self.session_manager.resume_session(
                        self.session_id, last_sequence=last_sequence
                    )
                else:
                    session = await self.session_manager.get_session(
                        self.session_id, org_id=self.org_id
                    )
                    if session.transport_type not in (
                        TransportType.WEBRTC,
                        TransportType.WEBSOCKET,
                    ):
                        logger.info(
                            "livekit_session_transport_mismatch",
                            session_id=str(self.session_id),
                            transport=session.transport_type.value,
                        )
                    await self.session_manager.activate_session(self.session_id)

                self.response_generator.init_session(self.session_id)
                if self.org_id is not None:
                    self.response_generator.set_session_org(self.session_id, self.org_id)
                    self.pipeline.set_session_org(self.session_id, self.org_id)

                messages = await self.session_manager.get_messages(self.session_id)
                if messages:
                    self.response_generator.load_history(self.session_id, messages)

                await self.session_manager.commit()
                active_sessions.inc()
                livekit_room_lifecycle_total.labels(event="session_prepared").inc()
            except SessionNotFoundError:
                livekit_room_lifecycle_total.labels(event="session_not_found").inc()
                raise

    def set_data_sender(self, sender: Callable[[dict], Awaitable[None]]) -> None:
        self._send_data = sender

    async def start(self, audio_frames: AsyncIterator[IncomingAudioFrame]) -> None:
        callbacks = build_livekit_callbacks(
            self.audio_publisher,
            on_data_message=self._send_data,
        )
        self._listening_task = asyncio.create_task(
            self._continuous_listening(callbacks),
            name=f"livekit-listen-{self.session_id}",
        )
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(),
            name=f"livekit-heartbeat-{self.session_id}",
        )
        self._ingress_task = asyncio.create_task(
            self._ingress_audio(audio_frames),
            name=f"livekit-ingress-{self.session_id}",
        )
        livekit_room_lifecycle_total.labels(event="started").inc()

    async def wait_until_done(self) -> None:
        tasks = [t for t in (self._ingress_task, self._listening_task) if t is not None]
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            if exc := task.exception():
                raise exc

    async def shutdown(self, *, reason: str = "normal") -> None:
        if self._shutdown.is_set():
            return
        self._shutdown.set()
        livekit_room_lifecycle_total.labels(event="shutdown").inc()
        for task in (self._ingress_task, self._listening_task, self._heartbeat_task):
            if task and not task.done():
                task.cancel()
        await self._audio_queue.put(None)
        try:
            await self.session_manager.end_session(self.session_id, reason=reason)
            await self.session_manager.commit()
        except Exception as exc:
            logger.warning(
                "livekit_session_end_failed",
                session_id=str(self.session_id),
                error=str(exc),
            )
        self.response_generator.clear_session(self.session_id)
        active_sessions.dec()

    async def handle_participant_connected(self, identity: str) -> None:
        livekit_participant_events_total.labels(event="connected").inc()
        logger.info(
            "livekit_participant_connected",
            session_id=str(self.session_id),
            identity=identity,
        )

    async def handle_participant_disconnected(self, identity: str, *, reason: str) -> None:
        livekit_participant_events_total.labels(event="disconnected").inc()
        logger.info(
            "livekit_participant_disconnected",
            session_id=str(self.session_id),
            identity=identity,
            reason=reason,
        )

    async def handle_reconnect(self, last_sequence: int = 0) -> None:
        livekit_reconnection_attempts_total.inc()
        with _tracer.start_as_current_span("livekit.session.reconnect"):
            await self.session_manager.resume_session(self.session_id, last_sequence=last_sequence)
            await self.session_manager.commit()
            logger.info(
                "livekit_session_reconnected",
                session_id=str(self.session_id),
                last_sequence=last_sequence,
            )

    async def handle_client_interrupt(self) -> None:
        """Browser push-to-talk / barge-in while agent is speaking."""
        livekit_barge_in_total.inc()
        clear = getattr(self.audio_publisher, "clear", None)
        if callable(clear):
            clear()
        await self.pipeline.interrupt(self.session_id)
        if self._send_data:
            try:
                await self._send_data({"type": "interrupted"})
            except Exception:
                pass
        logger.info("livekit_client_interrupt", session_id=str(self.session_id))

    async def _continuous_listening(self, callbacks) -> None:
        while not self._shutdown.is_set():
            try:
                turn_started = time.monotonic()
                await self.pipeline.run_listening(
                    self.session_id,
                    self._audio_queue,
                    callbacks,
                    language=self.language,
                )
                livekit_streaming_latency_seconds.observe(time.monotonic() - turn_started)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "livekit_listening_error",
                    session_id=str(self.session_id),
                    error=str(exc),
                )
                break

    async def _ingress_audio(self, audio_frames: AsyncIterator[IncomingAudioFrame]) -> None:
        async for frame in audio_frames:
            if self._shutdown.is_set():
                break
            received_at = time.monotonic()
            pcm = frame_to_pipeline_pcm(
                bytes(frame.data),
                sample_rate=frame.sample_rate,
                num_channels=frame.num_channels,
                received_at=received_at,
            )
            if pcm:
                await self._maybe_barge_in()
                try:
                    self._audio_queue.put_nowait(pcm)
                except asyncio.QueueFull:
                    # Drop oldest frame so STT/turn detection can keep up (Safari mic floods).
                    try:
                        _ = self._audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    try:
                        self._audio_queue.put_nowait(pcm)
                    except asyncio.QueueFull:
                        logger.warning(
                            "livekit_audio_queue_full",
                            session_id=str(self.session_id),
                        )

    async def _maybe_barge_in(self) -> None:
        phase = await self.session_manager.get_session_phase(self.session_id)
        if phase == SessionPhase.SPEAKING:
            livekit_barge_in_total.inc()
            clear = getattr(self.audio_publisher, "clear", None)
            if callable(clear):
                clear()
            await self.pipeline.interrupt(self.session_id)

    async def _heartbeat_loop(self) -> None:
        while not self._shutdown.is_set():
            await asyncio.sleep(self.settings.session_heartbeat_interval_seconds)
            await self.session_manager.record_heartbeat(self.session_id)

    @staticmethod
    async def send_json_data(
        publish_fn: Callable[..., Awaitable[None]],
        payload: dict[str, Any],
    ) -> None:
        # livekit-rtc >=1.x: topic is keyword-only (positional topic breaks publish_data).
        await publish_fn(json.dumps(payload).encode("utf-8"), topic="voxforge")
