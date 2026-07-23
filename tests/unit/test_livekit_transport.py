"""Unit tests for LiveKit room utilities and audio bridge."""

from uuid import uuid4

import pytest

from voxforge.core.domain.events import AudioChunk
from voxforge.infrastructure.livekit.audio_bridge import (
    PIPELINE_SAMPLE_RATE,
    chunk_to_livekit_frame,
    frame_to_pipeline_pcm,
)
from voxforge.infrastructure.livekit.room_utils import parse_session_id, room_name_for_session


def test_room_name_roundtrip():
    session_id = uuid4()
    room = room_name_for_session(session_id)
    assert parse_session_id(room) == session_id


def test_parse_session_id_rejects_invalid_prefix():
    with pytest.raises(ValueError, match="voxforge-"):
        parse_session_id("other-room")


def test_frame_to_pipeline_pcm_downsamples():
    # 48 kHz tone-like samples (960 samples = 20 ms)
    samples = [1000 if i % 2 == 0 else -1000 for i in range(960)]
    import struct

    data = struct.pack(f"<{len(samples)}h", *samples)
    pcm = frame_to_pipeline_pcm(data, sample_rate=48_000, num_channels=1)
    assert len(pcm) == (960 // 3) * 2


def test_chunk_to_livekit_frame_preserves_rate():
    chunk = AudioChunk(data=b"\x00\x01" * 160, sample_rate=PIPELINE_SAMPLE_RATE)
    frame = chunk_to_livekit_frame(chunk)
    assert frame.sample_rate == PIPELINE_SAMPLE_RATE
    assert frame.num_channels == 1


def test_chunk_to_livekit_frame_keeps_cartesia_rate_when_targeted():
    chunk = AudioChunk(data=b"\x00\x01" * 240, sample_rate=24_000)
    frame = chunk_to_livekit_frame(chunk, target_sample_rate=24_000)
    assert frame.sample_rate == 24_000
    assert len(frame.data) == 480
