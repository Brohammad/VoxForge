"""Bounded audio queue behavior for the voice WebSocket."""

import asyncio

from voxforge.api.ws.voice import _enqueue_audio_frame, _signal_audio_end


def test_enqueue_audio_frame_drops_oldest_when_full():
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=2)
    queue.put_nowait(b"oldest")
    queue.put_nowait(b"newer")

    overflowed = _enqueue_audio_frame(queue, b"newest")

    assert overflowed is True
    assert queue.get_nowait() == b"newer"
    assert queue.get_nowait() == b"newest"


def test_signal_audio_end_never_blocks_on_full_queue():
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=2)
    queue.put_nowait(b"oldest")
    queue.put_nowait(b"newer")

    _signal_audio_end(queue)

    assert queue.qsize() == 1
    assert queue.get_nowait() is None
