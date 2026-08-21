"""Publish pipeline TTS audio to a LiveKit room."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from voxforge.core.domain.events import AudioChunk
from voxforge.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from livekit import rtc

logger = get_logger(__name__)

# Cartesia TTS is 24 kHz; LiveKit agents typically publish at 48 kHz for WebRTC.
TTS_SAMPLE_RATE = 24_000
PUBLISH_SAMPLE_RATE = 48_000
_FRAME_MS = 10


class AudioPublisher(Protocol):
    async def publish_chunk(self, chunk: AudioChunk) -> None: ...

    async def flush(self) -> None: ...

    def clear(self) -> None: ...


class LiveKitAudioPublisher:
    """Publishes TTS PCM to LiveKit at 48 kHz using the RTC AudioResampler."""

    def __init__(
        self,
        source: rtc.AudioSource,
        *,
        sample_rate: int = PUBLISH_SAMPLE_RATE,
        mirror_afplay: bool = False,
    ) -> None:
        from livekit import rtc as _rtc

        self._rtc = _rtc
        self._source = source
        self._sample_rate = sample_rate
        self._bytes_per_frame = sample_rate * _FRAME_MS // 1000 * 2
        self._pending = bytearray()
        self._turn_pcm = bytearray()  # published-rate PCM for optional recording hooks
        self._mirror_afplay = mirror_afplay  # kept for API compat; unused (client hears)
        self._lock = asyncio.Lock()
        self._resampler = _rtc.AudioResampler(
            TTS_SAMPLE_RATE,
            sample_rate,
            num_channels=1,
            quality=_rtc.AudioResamplerQuality.HIGH,
        )

    def clear(self) -> None:
        """Drop queued TTS (barge-in)."""
        self._pending.clear()
        self._turn_pcm.clear()
        try:
            self._source.clear_queue()
        except Exception as exc:
            logger.warning("livekit_clear_queue_failed", error=str(exc))

    async def publish_chunk(self, chunk: AudioChunk) -> None:
        data = chunk.data
        if len(data) % 2 == 1:
            data = data[:-1]
        if not data:
            return

        src_rate = chunk.sample_rate or TTS_SAMPLE_RATE
        samples = len(data) // 2
        frame_in = self._rtc.AudioFrame(
            data=data,
            sample_rate=src_rate,
            num_channels=1,
            samples_per_channel=samples,
        )

        if src_rate == self._sample_rate:
            out_frames = [frame_in]
        else:
            if src_rate != TTS_SAMPLE_RATE:
                # Unexpected rate: rebuild resampler for this chunk's rate.
                self._resampler = self._rtc.AudioResampler(
                    src_rate,
                    self._sample_rate,
                    num_channels=1,
                    quality=self._rtc.AudioResamplerQuality.HIGH,
                )
            out_frames = self._resampler.push(frame_in)

        async with self._lock:
            for frame in out_frames:
                self._pending.extend(bytes(frame.data))
                self._turn_pcm.extend(bytes(frame.data))
            await self._drain_pending_locked()

    async def flush(self) -> None:
        async with self._lock:
            for frame in self._resampler.flush():
                self._pending.extend(bytes(frame.data))
                self._turn_pcm.extend(bytes(frame.data))
            if self._pending:
                if len(self._pending) % 2 == 1:
                    self._pending.append(0)
                if 0 < len(self._pending) < self._bytes_per_frame:
                    self._pending.extend(b"\x00" * (self._bytes_per_frame - len(self._pending)))
                await self._drain_pending_locked()
            self._turn_pcm.clear()

    async def _drain_pending_locked(self) -> None:
        while len(self._pending) >= self._bytes_per_frame:
            frame_bytes = bytes(self._pending[: self._bytes_per_frame])
            del self._pending[: self._bytes_per_frame]
            frame = self._rtc.AudioFrame(
                data=frame_bytes,
                sample_rate=self._sample_rate,
                num_channels=1,
                samples_per_channel=len(frame_bytes) // 2,
            )
            try:
                await self._source.capture_frame(frame)
            except Exception as exc:
                logger.warning("livekit_capture_frame_failed", error=str(exc))


class NullAudioPublisher:
    async def publish_chunk(self, chunk: AudioChunk) -> None:
        return None

    async def flush(self) -> None:
        return None

    def clear(self) -> None:
        return None
