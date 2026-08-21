"""Feature test: conversation → evaluation → replay → signed URL."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from voxforge.infrastructure.db.models import (
    EvaluationMetricModel,
    EvaluationRunModel,
    MessageModel,
    OrganizationModel,
    VoiceSessionModel,
)
from voxforge.infrastructure.db.replay_repository import ReplayRepository
from voxforge.modules.handoff.application.replay_link import ReplayLinkService
from voxforge.modules.replay.application.service import ReplayService

pytestmark = pytest.mark.feature


@pytest.mark.asyncio
async def test_replay_timeline_includes_evaluations(db_session):
    org_id = uuid4()
    session_id = uuid4()
    now = datetime.now(UTC)

    db_session.add(OrganizationModel(id=org_id, name="Replay Org", slug=f"rp-{org_id.hex[:8]}"))
    db_session.add(
        VoiceSessionModel(
            id=session_id,
            org_id=org_id,
            status="completed",
            transport_type="websocket",
            started_at=now,
            ended_at=now,
        )
    )
    db_session.add(
        MessageModel(
            session_id=session_id,
            role="user",
            content="Where is my order?",
            content_type="text",
            created_at=now,
        )
    )
    run_id = uuid4()
    db_session.add(
        EvaluationRunModel(
            id=run_id,
            org_id=org_id,
            session_id=session_id,
            user_transcript="Where is my order?",
            assistant_response="Your order ships tomorrow.",
            overall_score=0.88,
            overall_status="passed",
            created_at=now,
        )
    )
    db_session.add(
        EvaluationMetricModel(
            run_id=run_id,
            name="task_completion",
            score=0.9,
            status="passed",
        )
    )
    await db_session.commit()

    service = ReplayService(ReplayRepository(db_session))
    replay = await service.get_session_replay(session_id, org_id=org_id)
    assert replay.session_id == session_id
    assert any(e.event_type == "message" for e in replay.events)
    assert any(e.event_type == "evaluation" for e in replay.events)


@pytest.mark.asyncio
async def test_replay_link_generate_and_verify(handoff_settings_from_env):
    from voxforge.config import get_settings

    settings = get_settings()
    service = ReplayLinkService(settings)
    session_id = uuid4()
    org_id = uuid4()
    handoff_id = uuid4()

    url, token = service.generate(session_id=session_id, org_id=org_id, handoff_id=handoff_id)
    assert str(session_id) in url
    assert service.verify(session_id=session_id, org_id=org_id, handoff_id=handoff_id, token=token)


@pytest.fixture
def handoff_settings_from_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-at-least-32-bytes-long")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    from voxforge.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
