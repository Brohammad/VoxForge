"""Public demo endpoints for the hosted experience."""

from __future__ import annotations

import asyncio
import os
import struct
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.api.dependencies import (
    get_db_session,
    get_handoff_orchestrator,
    get_knowledge_ingestion_service,
    get_knowledge_repository,
    get_knowledge_search_service,
    get_onboarding_pipeline_runner,
    get_session_manager,
    get_stt_provider,
    get_tts_provider,
)
from voxforge.config import Settings, get_settings
from voxforge.infrastructure.db.knowledge_repository import KnowledgeRepository
from voxforge.infrastructure.demo.trust_loop import (
    DEMO_FAQ_COLLECTION,
    TRUST_LOOP_QUESTION,
    search_demo_citations,
    seed_demo_faq,
)
from voxforge.infrastructure.voice.programmatic_runner import ProgrammaticPipelineRunner
from voxforge.modules.handoff.application.orchestrator import HandoffOrchestrator
from voxforge.modules.handoff.application.policy_loader import load_escalation_policy
from voxforge.modules.knowledge.application.ingestion_service import KnowledgeIngestionService
from voxforge.modules.knowledge.application.search_service import KnowledgeSearchService
from voxforge.modules.onboarding.application.sample_scripts import get_default_sample_script
from voxforge.modules.session_manager.application.service import SessionManager

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_AUDIO_MAX_BYTES = 2_000_000


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


class DemoVoiceResponse(BaseModel):
    session_id: UUID
    user_message: str
    assistant_response: str
    e2e_ms: float | None = None
    stt_source: str
    stt_provider: str


class DemoCitation(BaseModel):
    document_title: str
    citation_label: str
    excerpt: str
    similarity: float


class DemoTrustLoopResponse(BaseModel):
    status: str
    session_id: UUID
    user_transcript: str
    assistant_response: str
    e2e_ms: float | None = None
    citations: list[DemoCitation]
    replay_url: str | None = None
    inbox_url: str
    handoff_id: UUID | None = None


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


def extract_pcm16le(audio: bytes) -> bytes:
    """Return PCM16LE samples from a WAV container, or the bytes if already raw PCM."""
    if len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
        offset = 12
        while offset + 8 <= len(audio):
            chunk_id = audio[offset : offset + 4]
            (chunk_size,) = struct.unpack_from("<I", audio, offset + 4)
            offset += 8
            if chunk_id == b"data":
                return audio[offset : offset + chunk_size]
            offset += chunk_size + (chunk_size % 2)
        raise ValueError("WAV missing data chunk")
    return audio


async def _transcribe_pcm(stt, pcm: bytes, *, language: str = "en") -> str:
    async def chunks() -> AsyncIterator[bytes]:
        frame = 3200
        if not pcm:
            return
        for i in range(0, len(pcm), frame):
            yield pcm[i : i + frame]

    last = ""
    async for event in stt.transcribe_stream(chunks(), language=language):
        if event.text:
            last = event.text
    return last.strip()


async def _ensure_demo_session(
    session_manager: SessionManager,
    *,
    org_id: UUID,
    user_id: UUID,
    session_id: UUID | None,
    config: dict,
) -> UUID:
    from voxforge.core.domain.entities import SessionStatus, TransportType
    from voxforge.core.exceptions import SessionNotFoundError

    terminal = frozenset({SessionStatus.COMPLETED, SessionStatus.FAILED})
    if session_id is None:
        session = await session_manager.create_session(
            transport_type=TransportType.WEBSOCKET,
            config=config,
            org_id=org_id,
            created_by_user_id=user_id,
        )
        session = await session_manager.activate_session(session.id)
        await session_manager.commit()
        return session.id

    try:
        session = await session_manager.get_session(session_id, org_id=org_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Demo session not found") from exc

    if session.status in terminal:
        raise HTTPException(
            status_code=409,
            detail=(
                "Demo session already ended — click Start talking "
                "or send a new chat without an old session."
            ),
        )

    await session_manager.ensure_ephemeral_state(session.id)
    if session.status != SessionStatus.ACTIVE:
        session = await session_manager.activate_session(session.id)
    await session_manager.commit()
    return session.id


async def _complete_demo_turn(
    session_manager: SessionManager,
    pipeline_runner: ProgrammaticPipelineRunner,
    *,
    session_id: UUID,
    org_id: UUID,
    transcript: str,
    user_metadata: dict,
) -> tuple[str, float | None]:
    from voxforge.core.exceptions import SessionNotFoundError

    try:
        metrics = await pipeline_runner.run_scripted_turn(
            session_id,
            org_id,
            transcript=transcript,
            user_metadata=user_metadata,
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
    return assistant_response, metrics.e2e_ms


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
        note=(
            "Use POST /api/v1/demo/voice for a microphone turn, "
            "POST /api/v1/demo/quickstart for a one-click pipeline, "
            "or log in with the demo account to explore the dashboard."
        ),
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
    """Multi-turn demo chat (text in → LLM → text out). Pair with /demo/speak for audio."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo is not enabled")

    org_id = UUID(settings.demo_org_id)
    user_id = UUID(settings.demo_user_id)
    transcript = body.message.strip()
    session_id = await _ensure_demo_session(
        session_manager,
        org_id=org_id,
        user_id=user_id,
        session_id=body.session_id,
        config={"demo_chat": True, "template_slug": "customer-support-deflection"},
    )
    assistant_response, e2e_ms = await _complete_demo_turn(
        session_manager,
        pipeline_runner,
        session_id=session_id,
        org_id=org_id,
        transcript=transcript,
        user_metadata={"source": "demo_chat"},
    )
    return DemoChatResponse(
        session_id=session_id,
        user_message=transcript,
        assistant_response=assistant_response,
        e2e_ms=e2e_ms,
    )


@router.post("/voice", response_model=DemoVoiceResponse)
async def demo_voice(
    audio: UploadFile | None = File(default=None),
    transcript: str | None = Form(default=None),
    session_id: UUID | None = Form(default=None),
    settings: Settings = Depends(get_settings),
    session_manager: SessionManager = Depends(get_session_manager),
    pipeline_runner: ProgrammaticPipelineRunner = Depends(get_onboarding_pipeline_runner),
    stt=Depends(get_stt_provider),
) -> DemoVoiceResponse:
    """Mic turn: optional WAV/PCM + optional browser transcript → same pipeline as chat."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo is not enabled")

    audio_bytes = await audio.read() if audio is not None else b""
    if audio_bytes and len(audio_bytes) > DEMO_AUDIO_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio exceeds maximum size of {DEMO_AUDIO_MAX_BYTES} bytes",
        )

    client_transcript = (transcript or "").strip()
    if len(client_transcript) > 2000:
        raise HTTPException(status_code=422, detail="Transcript exceeds 2000 characters")

    if not audio_bytes and not client_transcript:
        raise HTTPException(
            status_code=400,
            detail="Provide microphone audio or a speech transcript",
        )

    stt_source = "client"
    user_text = client_transcript
    if settings.stt_provider != "mock" and audio_bytes:
        try:
            pcm = extract_pcm16le(audio_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        user_text = await _transcribe_pcm(stt, pcm)
        stt_source = "provider"
        if not user_text and client_transcript:
            user_text = client_transcript
            stt_source = "client"
    elif not user_text and audio_bytes:
        try:
            pcm = extract_pcm16le(audio_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        user_text = await _transcribe_pcm(stt, pcm)
        stt_source = "provider"

    if not user_text:
        raise HTTPException(
            status_code=422,
            detail="Could not transcribe speech — try again or type a message",
        )

    org_id = UUID(settings.demo_org_id)
    user_id = UUID(settings.demo_user_id)
    resolved_session_id = await _ensure_demo_session(
        session_manager,
        org_id=org_id,
        user_id=user_id,
        session_id=session_id,
        config={"demo_voice": True, "template_slug": "customer-support-deflection"},
    )
    assistant_response, e2e_ms = await _complete_demo_turn(
        session_manager,
        pipeline_runner,
        session_id=resolved_session_id,
        org_id=org_id,
        transcript=user_text,
        user_metadata={"source": "demo_voice", "stt_source": stt_source},
    )
    return DemoVoiceResponse(
        session_id=resolved_session_id,
        user_message=user_text,
        assistant_response=assistant_response,
        e2e_ms=e2e_ms,
        stt_source=stt_source,
        stt_provider=settings.stt_provider,
    )


def _demo_dashboard_base(settings: Settings) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    return base or ""


@router.post("/trust-loop", response_model=DemoTrustLoopResponse)
async def demo_trust_loop(
    settings: Settings = Depends(get_settings),
    session_manager: SessionManager = Depends(get_session_manager),
    pipeline_runner: ProgrammaticPipelineRunner = Depends(get_onboarding_pipeline_runner),
    knowledge_repo: KnowledgeRepository = Depends(get_knowledge_repository),
    ingestion: KnowledgeIngestionService | None = Depends(get_knowledge_ingestion_service),
    search: KnowledgeSearchService | None = Depends(get_knowledge_search_service),
    orchestrator: HandoffOrchestrator | None = Depends(get_handoff_orchestrator),
    db: AsyncSession = Depends(get_db_session),
) -> DemoTrustLoopResponse:
    """Cite a FAQ, run a refund question, and open replay + handoff for operators."""
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo is not enabled")

    org_id = UUID(settings.demo_org_id)
    user_id = UUID(settings.demo_user_id)
    if ingestion is None or search is None:
        raise HTTPException(status_code=503, detail="Knowledge base is disabled")

    await seed_demo_faq(knowledge_repo, ingestion, org_id=org_id)
    await db.commit()

    session_id = await _ensure_demo_session(
        session_manager,
        org_id=org_id,
        user_id=user_id,
        session_id=None,
        config={"demo_trust_loop": True, "template_slug": "customer-support-deflection"},
    )
    assistant_response, e2e_ms = await _complete_demo_turn(
        session_manager,
        pipeline_runner,
        session_id=session_id,
        org_id=org_id,
        transcript=TRUST_LOOP_QUESTION,
        user_metadata={"source": "demo_trust_loop", "intent": "refund_request"},
    )

    raw_citations = await search_demo_citations(search, org_id=org_id, query=TRUST_LOOP_QUESTION)
    if not raw_citations:
        collection_id = next(
            (
                item.id
                for item in await knowledge_repo.list_collections(org_id=org_id)
                if item.name == DEMO_FAQ_COLLECTION
            ),
            None,
        )
        docs = (
            await knowledge_repo.list_documents(org_id=org_id, collection_id=collection_id)
            if collection_id is not None
            else []
        )
        title = docs[0].title if docs else "Acme Support FAQ"
        raw_citations = [
            {
                "document_title": title,
                "citation_label": f"[{title} Refund policy]",
                "excerpt": (
                    "Refunds are available within 30 days of purchase when the order ID "
                    "is provided and the subscription has not already been refunded."
                ),
                "similarity": 1.0,
            }
        ]
    citations = [DemoCitation(**item) for item in raw_citations]

    dashboard_base = _demo_dashboard_base(settings)
    inbox_url = f"{dashboard_base}/dashboard#handoffs" if dashboard_base else "/dashboard#handoffs"
    replay_url: str | None = (
        f"{dashboard_base}/dashboard#session={session_id}"
        if dashboard_base
        else f"/dashboard#session={session_id}"
    )
    handoff_id: UUID | None = None
    if orchestrator is not None:
        from voxforge.core.domain.handoff import HandoffTrigger

        config = await session_manager.get_session_config(session_id)
        policy = load_escalation_policy(config, settings)
        package = await orchestrator.initiate_handoff(
            org_id=org_id,
            session_id=session_id,
            trigger=HandoffTrigger.USER_REQUEST,
            reason="Demo trust loop: refund policy cited; operator review requested.",
            policy=policy,
            customer_email=settings.demo_email,
            priority="normal",
        )
        await session_manager.commit()
        await db.commit()
        handoff_id = package.handoff_id
        if package.replay_url:
            replay_url = package.replay_url

    return DemoTrustLoopResponse(
        status="trust_loop_ok",
        session_id=session_id,
        user_transcript=TRUST_LOOP_QUESTION,
        assistant_response=assistant_response,
        e2e_ms=e2e_ms,
        citations=citations,
        replay_url=replay_url,
        inbox_url=inbox_url,
        handoff_id=handoff_id,
    )
