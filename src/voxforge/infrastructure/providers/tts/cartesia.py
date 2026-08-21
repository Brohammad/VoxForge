from collections.abc import AsyncIterator

import httpx

from voxforge.core.domain.events import AudioChunk
from voxforge.core.exceptions import ProviderError
from voxforge.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

CARTESIA_TTS_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_API_VERSION = "2024-06-10"


class CartesiaTTSProvider:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        *,
        voice_id: str,
    ) -> AsyncIterator[AudioChunk]:
        if not self._api_key:
            raise ProviderError("cartesia", "API key not configured")

        async for text in text_stream:
            if not text.strip():
                continue
            async for chunk in self._synthesize_text(text, voice_id):
                yield chunk

    async def _synthesize_text(self, text: str, voice_id: str) -> AsyncIterator[AudioChunk]:
        headers = {
            "X-API-Key": self._api_key,
            "Cartesia-Version": CARTESIA_API_VERSION,
            "Content-Type": "application/json",
        }
        payload = {
            "model_id": "sonic-2",
            "transcript": text,
            "voice": {"mode": "id", "id": voice_id},
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 24000,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST", CARTESIA_TTS_URL, headers=headers, json=payload
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        raise ProviderError(
                            "cartesia",
                            f"HTTP {response.status_code}: {body.decode()}",
                        )
                    leftover = b""
                    async for raw in response.aiter_bytes(chunk_size=4096):
                        if not raw:
                            continue
                        data = leftover + raw
                        # Never split a 16-bit sample across AudioChunk boundaries.
                        if len(data) % 2 == 1:
                            leftover = data[-1:]
                            data = data[:-1]
                        else:
                            leftover = b""
                        if data:
                            yield AudioChunk(data=data, sample_rate=24000, encoding="pcm_s16le")
                    if len(leftover) == 1:
                        yield AudioChunk(
                            data=leftover + b"\x00",
                            sample_rate=24000,
                            encoding="pcm_s16le",
                        )
        except httpx.HTTPError as exc:
            logger.error("cartesia_tts_error", error=str(exc))
            raise ProviderError("cartesia", str(exc)) from exc


class SentenceBuffer:
    """Buffer token stream into sentence-boundary chunks for TTS."""

    SENTENCE_ENDINGS = {".", "!", "?", ";", "\n"}

    def __init__(self) -> None:
        self._buffer = ""

    def add(self, token: str) -> str | None:
        self._buffer += token
        for i in range(len(self._buffer) - 1, -1, -1):
            if self._buffer[i] in self.SENTENCE_ENDINGS:
                sentence = self._buffer[: i + 1].strip()
                self._buffer = self._buffer[i + 1 :]
                if sentence:
                    return sentence
        return None

    def flush(self) -> str | None:
        remaining = self._buffer.strip()
        self._buffer = ""
        return remaining if remaining else None


async def token_stream_to_sentences(token_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """Convert a token stream into sentence-boundary text chunks."""
    buffer = SentenceBuffer()
    async for token in token_stream:
        sentence = buffer.add(token)
        if sentence:
            yield sentence
    remaining = buffer.flush()
    if remaining:
        yield remaining
