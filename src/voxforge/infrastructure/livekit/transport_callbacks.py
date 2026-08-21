"""Pipeline callbacks for LiveKit transport (no duplicate business logic)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from voxforge.core.domain.events import AudioChunk, TranscriptEvent
from voxforge.infrastructure.livekit.audio_publisher import AudioPublisher
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.modules.voice_gateway.application.pipeline import PipelineCallbacks

logger = get_logger(__name__)


def build_livekit_callbacks(
    publisher: AudioPublisher,
    *,
    on_data_message: Callable[[dict], Awaitable[None] | None] | None = None,
) -> PipelineCallbacks:
    async def on_transcript(event: TranscriptEvent) -> None:
        if on_data_message:
            await _maybe_await(
                on_data_message(
                    {
                        "type": "transcript",
                        "partial": event.is_partial,
                        "text": event.text,
                        "confidence": event.confidence,
                        "language": event.language,
                    }
                )
            )

    async def on_token(text: str) -> None:
        if on_data_message:
            await _maybe_await(on_data_message({"type": "response", "token": text}))

    async def on_audio(chunk: AudioChunk) -> None:
        await publisher.publish_chunk(chunk)

    async def on_metrics(metrics) -> None:
        flush = getattr(publisher, "flush", None)
        if callable(flush):
            try:
                await flush()
            except Exception as exc:
                logger.warning("livekit_audio_flush_failed", error=str(exc))
        if on_data_message:
            await _maybe_await(
                on_data_message(
                    {
                        "type": "metric",
                        "stt_ms": metrics.stt_ms,
                        "llm_first_token_ms": metrics.llm_first_token_ms,
                        "tts_first_byte_ms": metrics.tts_first_byte_ms,
                        "e2e_ms": metrics.e2e_ms,
                    }
                )
            )

    async def on_error(code: str, message: str) -> None:
        logger.warning("livekit_pipeline_error", code=code, message=message)
        if on_data_message:
            await _maybe_await(on_data_message({"type": "error", "code": code, "message": message}))

    async def on_agent_step(agent: str, status: str, payload: dict) -> None:
        if on_data_message:
            await _maybe_await(
                on_data_message(
                    {
                        "type": "agent_step",
                        "agent": agent,
                        "status": status,
                        **payload,
                    }
                )
            )

    return PipelineCallbacks(
        on_transcript=on_transcript,
        on_token=on_token,
        on_audio=on_audio,
        on_metrics=on_metrics,
        on_error=on_error,
        on_agent_step=on_agent_step,
    )


async def _maybe_await(result) -> None:
    import asyncio

    if asyncio.iscoroutine(result):
        try:
            await result
        except Exception as exc:
            # Data-channel failures must not abort STT/LLM/TTS audio.
            logger.warning("livekit_data_send_failed", error=str(exc))
