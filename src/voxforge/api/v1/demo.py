"""Public demo endpoints for the hosted experience."""

from __future__ import annotations

import asyncio
import os
import struct
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from voxforge.api.dependencies import (
    get_onboarding_pipeline_runner,
    get_session_manager,
    get_tts_provider,
)
from voxforge.config import Settings, get_settings
from voxforge.infrastructure.voice.programmatic_runner import ProgrammaticPipelineRunner
from voxforge.modules.onboarding.application.sample_scripts import get_default_sample_script
from voxforge.modules.session_manager.application.service import SessionManager

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoQuickstartResponse(BaseModel):
    status: str
    session_id: UUID | None = None
    user_transcript: str
    assistant_response: str | None = None
    e2e_ms: float | None = None
    script_id: str


class DemoAccountResponse(BaseModel):
    email: str
    password_hint: str
    org_name: str
    note: str
    stt_provider: str
    llm_provider: str
    tts_provider: str
    embedding_provider: str
    providers_mode: str  # mock | mixed | live


class DemoSpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class DemoHearResponse(BaseModel):
    ok: bool
    bytes: int
    method: str


class DemoChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None


class DemoChatResponse(BaseModel):
    session_id: UUID
    user_message: str
    assistant_response: str
    e2e_ms: float | None = None


def _pcm16le_to_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
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


async def _synthesize_wav(tts, text: str, voice_id: str | None) -> tuple[bytes, int]:
    async def text_once() -> AsyncIterator[str]:
        yield text

    chunks: list[bytes] = []
    sample_rate = 24000
    async for chunk in tts.synthesize_stream(text_once(), voice_id=voice_id):
        chunks.append(chunk.data)
        sample_rate = chunk.sample_rate or sample_rate

    if not chunks:
        raise HTTPException(status_code=502, detail="TTS returned no audio")

    wav = _pcm16le_to_wav(b"".join(chunks), sample_rate=sample_rate)
    return wav, sample_rate


@router.get("/info", response_model=DemoAccountResponse)
async def demo_info(settings: Settings = Depends(get_settings)) -> DemoAccountResponse:
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo is not enabled")
    providers = (
        settings.stt_provider,
        settings.llm_provider,
        settings.tts_provider,
        settings.embedding_provider,
    )
    if all(p == "mock" for p in providers):
        mode = "mock"
    elif all(p != "mock" for p in providers):
        mode = "live"
    else:
        mode = "mixed"
    return DemoAccountResponse(
        email=settings.demo_email,
        password_hint=settings.demo_password_hint,
        org_name="VoxForge Demo",
        note="Use POST /api/v1/demo/quickstart for a one-click pipeline experience, "
        "or log in with the demo account to explore the dashboard.",
        stt_provider=settings.stt_provider,
        llm_provider=settings.llm_provider,
        tts_provider=settings.tts_provider,
        embedding_provider=settings.embedding_provider,
        providers_mode=mode,
    )


@router.post("/quickstart", response_model=DemoQuickstartResponse)
async def demo_quickstart(
    settings: Settings = Depends(get_settings),
    session_manager: SessionManager = Depends(get_session_manager),
    pipeline_runner: ProgrammaticPipelineRunner = Depends(get_onboarding_pipeline_runner),
) -> DemoQuickstartResponse:
    """Run a sample turn and keep the session open for follow-up chat."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo is not enabled")

    from voxforge.core.domain.entities import TransportType

    org_id = UUID(settings.demo_org_id)
    user_id = UUID(settings.demo_user_id)
    script = get_default_sample_script()

    session = await session_manager.create_session(
        transport_type=TransportType.WEBSOCKET,
        config={
            "template_slug": "customer-support-deflection",
            "demo_quickstart": True,
            "script_id": script.script_id,
        },
        org_id=org_id,
        created_by_user_id=user_id,
    )
    session = await session_manager.activate_session(session.id)
    await session_manager.commit()

    try:
        metrics = await pipeline_runner.run_scripted_turn(
            session.id,
            org_id,
            transcript=script.user_transcript,
            user_metadata=script.user_metadata,
        )
        await session_manager.commit()
    except Exception as exc:
        await session_manager.end_session(session.id, reason="demo_quickstart_failed")
        await session_manager.commit()
        raise HTTPException(status_code=502, detail=f"Demo turn failed: {exc}") from exc

    assistant_response: str | None = None
    messages = await session_manager.get_messages(session.id)
    for message in reversed(messages):
        if message.role.value == "assistant":
            assistant_response = message.content
            break

    return DemoQuickstartResponse(
        status="demo_turn_ok",
        session_id=session.id,
        user_transcript=script.user_transcript,
        assistant_response=assistant_response,
        e2e_ms=metrics.e2e_ms,
        script_id=script.script_id,
    )


@router.post("/speak")
async def demo_speak(
    body: DemoSpeakRequest,
    settings: Settings = Depends(get_settings),
    tts=Depends(get_tts_provider),
) -> Response:
    """Synthesize assistant text to WAV for download / optional browser playback."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo is not enabled")

    wav, _sample_rate = await _synthesize_wav(tts, body.text, settings.default_tts_voice_id)
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "Accept-Ranges": "bytes",
            "Content-Disposition": 'inline; filename="assistant.wav"',
        },
    )


@router.post("/hear", response_model=DemoHearResponse)
async def demo_hear(
    body: DemoSpeakRequest,
    settings: Settings = Depends(get_settings),
    tts=Depends(get_tts_provider),
) -> DemoHearResponse:
    """Synthesize + play on the API host speakers via afplay (local demo only)."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo is not enabled")

    wav, _sample_rate = await _synthesize_wav(tts, body.text, settings.default_tts_voice_id)

    fd, path = tempfile.mkstemp(prefix="voxforge-demo-", suffix=".wav")
    os.close(fd)
    wav_path = Path(path)
    try:
        wav_path.write_bytes(wav)
        proc = await asyncio.create_subprocess_exec(
            "afplay",
            str(wav_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = (stderr or b"").decode("utf-8", errors="replace").strip()
            raise HTTPException(
                status_code=502,
                detail=f"afplay failed (code {proc.returncode}): {err or 'no stderr'}",
            )
    finally:
        wav_path.unlink(missing_ok=True)

    return DemoHearResponse(ok=True, bytes=len(wav), method="afplay")


@router.post("/chat", response_model=DemoChatResponse)
async def demo_chat(
    body: DemoChatRequest,
    settings: Settings = Depends(get_settings),
    session_manager: SessionManager = Depends(get_session_manager),
    pipeline_runner: ProgrammaticPipelineRunner = Depends(get_onboarding_pipeline_runner),
) -> DemoChatResponse:
    """Multi-turn demo chat (text in → LLM → text out). Pair with /demo/hear for audio."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo is not enabled")

    from voxforge.core.domain.entities import SessionStatus, TransportType
    from voxforge.core.exceptions import SessionNotFoundError

    org_id = UUID(settings.demo_org_id)
    user_id = UUID(settings.demo_user_id)
    terminal = frozenset({SessionStatus.COMPLETED, SessionStatus.FAILED})

    if body.session_id is None:
        session = await session_manager.create_session(
            transport_type=TransportType.WEBSOCKET,
            config={"demo_chat": True, "template_slug": "customer-support-deflection"},
            org_id=org_id,
            created_by_user_id=user_id,
        )
        session = await session_manager.activate_session(session.id)
        await session_manager.commit()
        session_id = session.id
    else:
        try:
            session = await session_manager.get_session(body.session_id, org_id=org_id)
        except SessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Demo session not found") from exc

        if session.status in terminal:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Demo session already ended — click Run sample call "
                    "or send a new chat without an old session."
                ),
            )

        # Redis state is required for turns; rebuild if TTL expired.
        await session_manager.ensure_ephemeral_state(session.id)
        if session.status != SessionStatus.ACTIVE:
            session = await session_manager.activate_session(session.id)
        await session_manager.commit()
        session_id = session.id

    try:
        metrics = await pipeline_runner.run_scripted_turn(
            session_id,
            org_id,
            transcript=body.message.strip(),
            user_metadata={"source": "demo_chat"},
        )
        await session_manager.commit()
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail="Demo session state expired — run sample call again to start a fresh session.",
        ) from exc

    assistant_response = ""
    messages = await session_manager.get_messages(session_id)
    for message in reversed(messages):
        if message.role.value == "assistant":
            assistant_response = message.content
            break

    if not assistant_response:
        raise HTTPException(status_code=502, detail="No assistant response generated")

    return DemoChatResponse(
        session_id=session_id,
        user_message=body.message.strip(),
        assistant_response=assistant_response,
        e2e_ms=metrics.e2e_ms,
    )
