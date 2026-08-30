from collections.abc import AsyncIterator
from typing import Protocol

from voxforge.core.domain.entities import MessageRole
from voxforge.core.domain.events import AudioChunk, TokenEvent, TranscriptEvent


class ChatMessage(Protocol):
    role: MessageRole
    content: str


class SpeechProvider(Protocol):
    def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        *,
        language: str | None = None,
    ) -> AsyncIterator[TranscriptEvent]:
        """Stream audio in, stream transcript events out."""
        ...


class LLMProvider(Protocol):
    def generate_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
    ) -> AsyncIterator[TokenEvent]:
        """Stream chat messages in, stream token events out."""
        ...


class TTSProvider(Protocol):
    def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        *,
        voice_id: str,
    ) -> AsyncIterator[AudioChunk]:
        """Stream text in, stream audio chunks out."""
        ...
