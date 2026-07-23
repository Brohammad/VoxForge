"""Publish pipeline TTS audio to a LiveKit room."""

from __future__ import annotations

import asyncio
import os
import struct
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from voxforge.core.domain.events import AudioChunk
from voxforge.infrastructure.livekit.audio_bridge import chunk_to_livekit_frame
from voxforge.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from livekit import rtc

logger = get_logger(__name__)

# Cartesia (and most pipeline TTS) is 24 kHz. Publishing at 16 kHz with
# per-chunk naive resampling sounds like noise/"waves" in the browser.
PUBLISH_SAMPLE_RATE = 24_000
# LiveKit / WebRTC expect ~10 ms frames for smooth playout.
_FRAME_MS = 10


class AudioPublisher(Protocol):
    async def publish_chunk(self, chunk: AudioChunk) -> None: ...

    async def flush(self) -> None: ...


def _pcm16le_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm


class LiveKitAudioPublisher:
    """Publishes PCM frames to a LiveKit ``AudioSource`` in 10 ms slices.

    Also mirrors complete turns to Mac speakers via ``afplay`` so local demos
    stay audible when Safari WebRTC playout is broken.
    """

    def __init__(
        self,
        source: rtc.AudioSource,
        *,
        sample_rate: int = PUBLISH_SAMPLE_RATE,
        mirror_afplay: bool = True,
    ) -> None:
        from livekit import rtc as _rtc

        self._rtc = _rtc
        self._source = source
        self._sample_rate = sample_rate
        self._bytes_per_frame = sample_rate * _FRAME_MS // 1000 * 2  # mono int16
        self._pending = bytearray()
        self._turn_pcm = bytearray()
        self._mirror_afplay = mirror_afplay
        self._lock = asyncio.Lock()

    async def publish_chunk(self, chunk: AudioChunk) -> None:
        pcm = chunk_to_livekit_frame(chunk, target_sample_rate=self._sample_rate)
        async with self._lock:
            self._pending.extend(pcm.data)
            self._turn_pcm.extend(pcm.data)
            while len(self._pending) >= self._bytes_per_frame:
                frame_bytes = bytes(self._pending[: self._bytes_per_frame])
                del self._pending[: self._bytes_per_frame]
                samples = len(frame_bytes) // 2
                frame = self._rtc.AudioFrame(
                    data=frame_bytes,
                    sample_rate=self._sample_rate,
                    num_channels=1,
                    samples_per_channel=samples,
                )
                try:
                    await self._source.capture_frame(frame)
                except Exception as exc:
                    logger.warning("livekit_capture_frame_failed", error=str(exc))

    async def flush(self) -> None:
        """Push leftover frames, then optionally afplay the full turn on this Mac."""
        turn_bytes = b""
        async with self._lock:
            if self._pending:
                if len(self._pending) % 2 == 1:
                    self._pending.append(0)
                if len(self._pending) < self._bytes_per_frame:
                    self._pending.extend(b"\x00" * (self._bytes_per_frame - len(self._pending)))
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
            turn_bytes = bytes(self._turn_pcm)
            self._turn_pcm.clear()

        if self._mirror_afplay and turn_bytes:
            await self._afplay(turn_bytes)

    async def _afplay(self, pcm: bytes) -> None:
        fd, path = tempfile.mkstemp(prefix="voxforge-lk-", suffix=".wav")
        os.close(fd)
        wav_path = Path(path)
        try:
            wav_path.write_bytes(_pcm16le_to_wav(pcm, self._sample_rate))
            proc = await asyncio.create_subprocess_exec(
                "afplay",
                str(wav_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = (stderr or b"").decode("utf-8", errors="replace").strip()
                logger.warning("livekit_afplay_failed", error=err or f"code={proc.returncode}")
            else:
                logger.info("livekit_afplay_ok", bytes=len(pcm))
        finally:
            wav_path.unlink(missing_ok=True)


class NullAudioPublisher:
    """No-op publisher for tests."""

    async def publish_chunk(self, chunk: AudioChunk) -> None:
        return None

    async def flush(self) -> None:
        return None
