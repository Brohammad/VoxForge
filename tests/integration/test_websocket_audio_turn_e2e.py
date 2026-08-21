"""E2E: audio ingress through the voice pipeline (mock STT → LLM → TTS → DB)."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from voxforge.config import get_settings
from voxforge.core.domain.entities import TransportType
from voxforge.core.events.bus import get_event_bus
from voxforge.infrastructure.redis.session_state import RedisSessionStateStore
from voxforge.modules.voice_gateway.application.pipeline import PipelineCallbacks
from voxforge.modules.voice_gateway.application.pipeline_factory import build_voice_pipeline_bundle


@pytest.mark.asyncio
async def test_run_listening_audio_turn_persists_messages(auth_client, fake_redis, db_engine):
    """PCM audio queue exercises the same path WebSocket bytes feed into the pipeline."""
    register = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"audio-turn-{uuid4().hex[:8]}@example.com",
            "password": "securepass123",
            "full_name": "Audio Turn User",
            "org_name": "Audio Turn Org",
        },
    )
    body = register.json()
    token = body["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org_id = UUID(body["org_id"])
    user_id = UUID(body["user_id"])

    settings = get_settings()
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    state_store = RedisSessionStateStore(fake_redis, ttl_seconds=settings.session_state_ttl_seconds)

    async with factory() as db_session:
        bundle = build_voice_pipeline_bundle(
            db_session,
            state_store,
            get_event_bus(),
            settings,
        )
        session = await bundle.session_manager.create_session(
            transport_type=TransportType.WEBSOCKET,
            config={"language": "en"},
            org_id=org_id,
            created_by_user_id=user_id,
        )
        session = await bundle.session_manager.activate_session(session.id)
        bundle.response_generator.init_session(session.id)
        bundle.response_generator.set_session_org(session.id, org_id)
        bundle.pipeline.set_session_org(session.id, org_id)

        audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        transcripts: list[str] = []
        callbacks = PipelineCallbacks(
            on_transcript=lambda event: transcripts.append(event.text),
        )

        task = asyncio.create_task(
            bundle.pipeline.run_listening(
                session.id,
                audio_queue,
                callbacks,
                language="en",
            )
        )
        await audio_queue.put(b"\x00\x01" * 1600)
        await audio_queue.put(None)
        await task
        await bundle.session_manager.commit()

    messages = await auth_client.get(
        f"/api/v1/sessions/{session.id}/messages",
        headers=headers,
    )
    assert messages.status_code == 200
    body = messages.json()["messages"]
    assert len(body) >= 2
    assert any("mock transcript" in m.get("content", "") for m in body)
    assert any(m.get("role") == "assistant" for m in body)
    assert transcripts
