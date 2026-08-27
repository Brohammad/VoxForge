"""Integration tests for public demo endpoints."""

import io
from uuid import UUID

import pytest

from voxforge.api.v1.demo import _pcm16le_to_wav, extract_pcm16le
from voxforge.config import get_settings
from voxforge.infrastructure.db.models import (
    OrganizationMemberModel,
    OrganizationModel,
    UserModel,
)

DEMO_ORG_ID = UUID("a0000000-0000-4000-8000-000000000001")
DEMO_USER_ID = UUID("a0000000-0000-4000-8000-000000000002")


@pytest.fixture
async def demo_seeded(db_session):
    db_session.add(OrganizationModel(id=DEMO_ORG_ID, name="VoxForge Demo", slug="voxforge-demo"))
    db_session.add(
        UserModel(
            id=DEMO_USER_ID,
            email="demo@voxforge.io",
            hashed_password="hash",
            full_name="Demo User",
        )
    )
    db_session.add(OrganizationMemberModel(org_id=DEMO_ORG_ID, user_id=DEMO_USER_ID, role="owner"))
    await db_session.commit()


@pytest.fixture
def demo_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_ENABLED", "true")
    monkeypatch.setenv("DEMO_ORG_ID", str(DEMO_ORG_ID))
    monkeypatch.setenv("DEMO_USER_ID", str(DEMO_USER_ID))
    monkeypatch.setenv("STT_PROVIDER", "mock")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("TTS_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("KNOWLEDGE_WORKER_ENABLED", "false")
    monkeypatch.setenv("KNOWLEDGE_BLOB_PATH", str(tmp_path / "kb"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_demo_info_when_enabled(test_client, demo_env, demo_seeded):
    res = await test_client.get("/api/v1/demo/info")
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "demo@voxforge.io"
    assert body["providers_mode"] in {"mock", "mixed", "live"}
    assert "stt_provider" in body


@pytest.mark.asyncio
async def test_demo_quickstart_runs_pipeline(test_client, demo_env, demo_seeded):
    res = await test_client.post("/api/v1/demo/quickstart")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "demo_turn_ok"
    assert body["session_id"]
    assert body["assistant_response"]
    assert body["e2e_ms"] is not None

    # Quickstart keeps the session open for follow-up /demo/chat turns.
    chat = await test_client.post(
        "/api/v1/demo/chat",
        json={"message": "Thanks, that helps.", "session_id": body["session_id"]},
    )
    assert chat.status_code == 200
    chat_body = chat.json()
    assert chat_body["session_id"] == body["session_id"]
    assert chat_body["assistant_response"]


@pytest.mark.asyncio
async def test_demo_voice_uses_client_transcript(test_client, demo_env, demo_seeded):
    pcm = b"\x00\x01" * 160
    wav = _pcm16le_to_wav(pcm, sample_rate=16000)
    res = await test_client.post(
        "/api/v1/demo/voice",
        files={"audio": ("speech.wav", io.BytesIO(wav), "audio/wav")},
        data={"transcript": "I need to change my billing contact"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_message"] == "I need to change my billing contact"
    assert "billing contact" in body["assistant_response"].lower()
    assert body["stt_source"] == "client"
    assert body["stt_provider"] == "mock"
    assert body["session_id"]


@pytest.mark.asyncio
async def test_demo_voice_audio_only_uses_mock_stt(test_client, demo_env, demo_seeded):
    pcm = b"\x00\x01" * 160
    wav = _pcm16le_to_wav(pcm, sample_rate=16000)
    res = await test_client.post(
        "/api/v1/demo/voice",
        files={"audio": ("speech.wav", io.BytesIO(wav), "audio/wav")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_message"] == "mock transcript"
    assert body["stt_source"] == "provider"
    assert body["assistant_response"]


@pytest.mark.asyncio
async def test_demo_voice_rejects_empty_payload(test_client, demo_env, demo_seeded):
    res = await test_client.post("/api/v1/demo/voice")
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_demo_voice_disabled_returns_404(test_client, monkeypatch):
    monkeypatch.setenv("DEMO_ENABLED", "false")
    get_settings.cache_clear()
    res = await test_client.post(
        "/api/v1/demo/voice",
        data={"transcript": "hello"},
    )
    assert res.status_code == 404
    get_settings.cache_clear()


def test_extract_pcm16le_from_wav():
    pcm = b"\x00\x01" * 16
    wav = _pcm16le_to_wav(pcm, sample_rate=16000)
    assert extract_pcm16le(wav) == pcm
    assert extract_pcm16le(pcm) == pcm


@pytest.mark.asyncio
async def test_demo_trust_loop_cites_and_handoffs(test_client, demo_env, demo_seeded):
    res = await test_client.post("/api/v1/demo/trust-loop")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "trust_loop_ok"
    assert body["session_id"]
    assert "refund" in body["user_transcript"].lower()
    assert "30 days" in body["assistant_response"].lower()
    assert body["citations"]
    assert body["citations"][0]["document_title"]
    assert body["replay_url"]
    assert "handoffs" in body["inbox_url"]
    assert body["handoff_id"]


@pytest.mark.asyncio
async def test_demo_disabled_returns_404(test_client, monkeypatch):
    monkeypatch.setenv("DEMO_ENABLED", "false")
    get_settings.cache_clear()
    res = await test_client.post("/api/v1/demo/quickstart")
    assert res.status_code == 404
    get_settings.cache_clear()
