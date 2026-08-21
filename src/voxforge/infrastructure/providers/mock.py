"""Mock providers for tests, CI eval gates, and local development without API keys."""

from collections.abc import AsyncIterator

from voxforge.core.domain.events import AudioChunk, TokenEvent, TranscriptEvent
from voxforge.core.interfaces.providers import ChatMessage


class MockSTTProvider:
    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        *,
        language: str | None = None,
    ) -> AsyncIterator[TranscriptEvent]:
        async for chunk in audio_stream:
            if chunk:
                yield TranscriptEvent(
                    text="mock transcript",
                    is_partial=True,
                    confidence=0.9,
                )
                yield TranscriptEvent(text="mock transcript", is_partial=False, confidence=1.0)
                return
        yield TranscriptEvent(text="mock transcript", is_partial=False, confidence=1.0)


class MockLLMProvider:
    async def generate_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
    ) -> AsyncIterator[TokenEvent]:
        last_user = next((m.content for m in reversed(messages) if m.role.value == "user"), "")
        lower_user = last_user.lower()
        if "billing contact" in lower_user:
            reply = "I can help with that. I verified your account and updated the billing contact."
        else:
            reply = f"Mock response to: {last_user[:80]}"
        yield TokenEvent(text=reply, is_final=False)
        yield TokenEvent(text="", is_final=True)


class MockTTSProvider:
    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        *,
        voice_id: str,
    ) -> AsyncIterator[AudioChunk]:
        async for _ in text_stream:
            pass
        yield AudioChunk(data=b"\x00" * 320, sample_rate=16000, encoding="pcm_s16le")
