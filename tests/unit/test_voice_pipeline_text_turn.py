import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from voxforge.core.domain.entities import TurnMetrics
from voxforge.core.domain.events import AudioChunk, TokenEvent
from voxforge.core.exceptions import SessionNotFoundError, UnauthorizedError
from voxforge.modules.voice_gateway.application.pipeline import (
    PipelineCallbacks,
    VoicePipelineService,
)


def _settings(**overrides):
    settings = MagicMock()
    settings.stt_provider = "mock"
    settings.tts_provider = "mock"
    settings.default_tts_voice_id = "voice-1"
    settings.knowledge_context_enabled = False
    settings.evaluation_enabled = False
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


@pytest.mark.asyncio
async def test_run_text_turn_skips_stt_and_returns_metrics():
    session_id = uuid4()
    expected = TurnMetrics(stt_ms=0.0, llm_first_token_ms=10.0, e2e_ms=50.0)

    pipeline = VoicePipelineService(
        session_manager=MagicMock(),
        stt_provider=MagicMock(),
        response_generator=MagicMock(),
        tts_provider=MagicMock(),
        settings=_settings(),
    )
    pipeline._process_turn = AsyncMock(return_value=expected)  # noqa: SLF001

    metrics = await pipeline.run_text_turn(
        session_id,
        "Hello there",
        user_metadata={"intent": "greeting"},
    )

    pipeline._process_turn.assert_awaited_once()  # noqa: SLF001
    call_kwargs = pipeline._process_turn.await_args.kwargs  # noqa: SLF001
    assert call_kwargs["stt_ms"] == 0.0
    assert call_kwargs["user_metadata_extra"] == {"intent": "greeting"}
    assert metrics.e2e_ms == 50.0


@pytest.mark.asyncio
async def test_process_turn_streams_tokens_and_audio():
    session_id = uuid4()
    user_message = MagicMock(id=uuid4())
    assistant_message = MagicMock(id=uuid4())

    sessions = MagicMock()
    sessions.update_phase = AsyncMock()
    sessions.save_user_message = AsyncMock(return_value=user_message)
    sessions.save_assistant_message = AsyncMock(return_value=assistant_message)
    sessions.save_turn_metrics = AsyncMock()
    sessions.get_session_config = AsyncMock(return_value={"voice_id": "custom-voice"})
    sessions.commit = AsyncMock()
    sessions.clear_interrupt = AsyncMock()
    sessions.set_interrupt = AsyncMock()

    async def gen_response(session_id, on_agent_step=None):
        yield TokenEvent(text="Hello ")
        yield TokenEvent(text="world.")

    response_generator = MagicMock()
    response_generator.generate_response = gen_response
    response_generator.add_user_message = MagicMock()
    response_generator.add_assistant_message = MagicMock()
    response_generator.get_last_agent_trace = MagicMock(return_value=[])

    async def synthesize_stream(text_iter, voice_id=None):
        assert voice_id == "custom-voice"
        async for _ in text_iter:
            yield AudioChunk(data=b"\x00\x01")

    tts = MagicMock()
    tts.synthesize_stream = synthesize_stream

    tokens: list[str] = []
    audio_chunks: list[bytes] = []
    callbacks = PipelineCallbacks(
        on_token=lambda t: tokens.append(t),
        on_audio=lambda c: audio_chunks.append(c.data),
    )

    pipeline = VoicePipelineService(
        session_manager=sessions,
        stt_provider=MagicMock(),
        response_generator=response_generator,
        tts_provider=tts,
        settings=_settings(),
    )

    metrics = await pipeline.run_text_turn(session_id, "Hi", callbacks=callbacks)

    assert "".join(tokens) == "Hello world."
    assert audio_chunks == [b"\x00\x01"]
    assert metrics.stt_ms == 0.0
    sessions.save_assistant_message.assert_awaited()
    sessions.save_turn_metrics.assert_awaited()


@pytest.mark.asyncio
async def test_listening_error_sends_safe_client_message():
    session_id = uuid4()
    errors: list[tuple[str, str]] = []

    async def broken_transcribe(audio_stream, language=None):
        raise RuntimeError("secret provider stacktrace")
        yield  # pragma: no cover

    stt = MagicMock()
    stt.transcribe_stream = broken_transcribe

    callbacks = PipelineCallbacks(
        on_error=lambda code, message: errors.append((code, message)),
    )
    pipeline = VoicePipelineService(
        session_manager=MagicMock(),
        stt_provider=stt,
        response_generator=MagicMock(),
        tts_provider=MagicMock(),
        settings=_settings(),
    )

    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(None)
    await pipeline.run_listening(session_id, queue, callbacks)

    assert errors == [("pipeline_error", "Voice pipeline failed")]


@pytest.mark.asyncio
async def test_tts_error_sends_safe_client_message():
    session_id = uuid4()
    errors: list[tuple[str, str]] = []

    sessions = MagicMock()
    sessions.update_phase = AsyncMock()
    sessions.save_user_message = AsyncMock(return_value=MagicMock(id=uuid4()))
    sessions.save_assistant_message = AsyncMock(return_value=MagicMock(id=uuid4()))
    sessions.save_turn_metrics = AsyncMock()
    sessions.get_session_config = AsyncMock(return_value={})
    sessions.commit = AsyncMock()
    sessions.clear_interrupt = AsyncMock()
    sessions.set_interrupt = AsyncMock()

    async def gen_response(session_id, on_agent_step=None):
        yield TokenEvent(text="Hello.")

    response_generator = MagicMock()
    response_generator.generate_response = gen_response
    response_generator.add_user_message = MagicMock()
    response_generator.add_assistant_message = MagicMock()
    response_generator.get_last_agent_trace = MagicMock(return_value=[])

    async def synthesize_stream(text_iter, voice_id=None):
        raise RuntimeError("cartesia api key leaked")
        yield  # pragma: no cover

    tts = MagicMock()
    tts.synthesize_stream = synthesize_stream

    pipeline = VoicePipelineService(
        session_manager=sessions,
        stt_provider=MagicMock(),
        response_generator=response_generator,
        tts_provider=tts,
        settings=_settings(),
    )
    callbacks = PipelineCallbacks(on_error=lambda c, m: errors.append((c, m)))

    await pipeline.run_text_turn(session_id, "Hi", callbacks=callbacks)

    assert errors == [("tts_error", "Speech synthesis failed")]


@pytest.mark.asyncio
async def test_voxforge_error_handler_returns_code():
    from fastapi import Request

    from voxforge.core.exceptions import VoxForgeError
    from voxforge.main import create_app

    app = create_app()
    handler = app.exception_handlers[VoxForgeError]
    request = MagicMock(spec=Request)
    response = await handler(request, SessionNotFoundError("abc"))
    assert response.status_code == 404
    assert b"session_not_found" in response.body


@pytest.mark.asyncio
async def test_unauthorized_error_handler():
    from fastapi import Request

    from voxforge.core.exceptions import VoxForgeError
    from voxforge.main import create_app

    app = create_app()
    handler = app.exception_handlers[VoxForgeError]
    request = MagicMock(spec=Request)
    response = await handler(request, UnauthorizedError("nope"))
    assert response.status_code == 401
    assert b"unauthorized" in response.body
