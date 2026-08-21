"""Unit tests for HandoffOrchestrator business logic."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tests.conftest import TEST_ORG_ID
from voxforge.config import get_settings
from voxforge.core.domain.handoff import (
    EscalationPolicy,
    HandoffStatus,
    HandoffTrigger,
)
from voxforge.core.events.bus import EventBus
from voxforge.infrastructure.db.handoff_repository import HandoffRepository
from voxforge.infrastructure.providers.support.mock import MockTicketingProvider
from voxforge.infrastructure.redis.session_state import RedisSessionStateStore
from voxforge.modules.handoff.application.orchestrator import HandoffOrchestrator
from voxforge.modules.handoff.application.replay_link import ReplayLinkService
from voxforge.modules.handoff.application.summarizer import ExtractiveConversationSummarizer
from voxforge.modules.session_manager.application.service import SessionManager


@pytest.fixture
def handoff_settings(monkeypatch):
    monkeypatch.setenv("HANDOFF_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-at-least-32-bytes-long")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
async def orchestrator(db_session, fake_redis, handoff_settings):
    store = RedisSessionStateStore(fake_redis)
    sessions = SessionManager(db_session, store, EventBus(), handoff_settings)
    repo = HandoffRepository(db_session)
    replay = ReplayLinkService(handoff_settings)
    summarizer = ExtractiveConversationSummarizer(sessions)
    return HandoffOrchestrator(
        repository=repo,
        ticketing=MockTicketingProvider(),
        summarizer=summarizer,
        replay_links=replay,
        session_manager=sessions,
        settings=handoff_settings,
    )


@pytest.fixture
async def active_session(orchestrator, db_session):
    session = await orchestrator._sessions.create_session(org_id=TEST_ORG_ID)  # noqa: SLF001
    await orchestrator._sessions.activate_session(session.id)  # noqa: SLF001
    await orchestrator._sessions.save_user_message(  # noqa: SLF001
        session.id,
        content="I need help with my order",
    )
    await orchestrator._sessions.save_assistant_message(  # noqa: SLF001
        session.id,
        content="I can look that up for you.",
    )
    await db_session.commit()
    return session


@pytest.mark.asyncio
async def test_initiate_handoff_creates_package(orchestrator, active_session, handoff_settings):
    org_id = TEST_ORG_ID
    policy = EscalationPolicy(auto_create_ticket=True)

    package = await orchestrator.initiate_handoff(
        org_id=org_id,
        session_id=active_session.id,
        trigger=HandoffTrigger.USER_REQUEST,
        reason="Customer asked for human",
        policy=policy,
    )
    await orchestrator._repo._session.commit()  # noqa: SLF001

    assert package.handoff_id is not None
    assert package.ticket_id is not None
    assert package.conversation_summary
    assert package.replay_url.startswith("http")
    assert package.trigger == HandoffTrigger.USER_REQUEST


@pytest.mark.asyncio
async def test_initiate_handoff_idempotent(orchestrator, active_session, handoff_settings):
    org_id = TEST_ORG_ID
    policy = EscalationPolicy()

    first = await orchestrator.initiate_handoff(
        org_id=org_id,
        session_id=active_session.id,
        trigger=HandoffTrigger.USER_REQUEST,
        reason="first",
        policy=policy,
    )
    second = await orchestrator.initiate_handoff(
        org_id=org_id,
        session_id=active_session.id,
        trigger=HandoffTrigger.USER_REQUEST,
        reason="second",
        policy=policy,
    )

    assert first.handoff_id == second.handoff_id
    assert first.ticket_id == second.ticket_id


@pytest.mark.asyncio
async def test_accept_and_complete_handoff(orchestrator, active_session, handoff_settings):
    org_id = TEST_ORG_ID
    user_id = uuid4()
    policy = EscalationPolicy()

    package = await orchestrator.initiate_handoff(
        org_id=org_id,
        session_id=active_session.id,
        trigger=HandoffTrigger.POLICY,
        reason="low confidence",
        policy=policy,
    )

    accepted = await orchestrator.accept_handoff(
        handoff_id=package.handoff_id,
        org_id=org_id,
        user_id=user_id,
    )
    assert accepted.status == HandoffStatus.ACTIVE

    completed = await orchestrator.complete_handoff(
        handoff_id=package.handoff_id,
        org_id=org_id,
        resolution="resolved",
    )
    assert completed.status == HandoffStatus.COMPLETED


@pytest.mark.asyncio
async def test_accept_handoff_idempotent_for_same_user(
    orchestrator, active_session, handoff_settings
):
    org_id = TEST_ORG_ID
    user_id = uuid4()
    policy = EscalationPolicy()

    package = await orchestrator.initiate_handoff(
        org_id=org_id,
        session_id=active_session.id,
        trigger=HandoffTrigger.USER_REQUEST,
        reason="help",
        policy=policy,
    )
    first = await orchestrator.accept_handoff(
        handoff_id=package.handoff_id, org_id=org_id, user_id=user_id
    )
    second = await orchestrator.accept_handoff(
        handoff_id=package.handoff_id, org_id=org_id, user_id=user_id
    )
    assert first.id == second.id


@pytest.mark.asyncio
async def test_accept_handoff_rejects_other_agent(orchestrator, active_session, handoff_settings):
    org_id = TEST_ORG_ID
    policy = EscalationPolicy()

    package = await orchestrator.initiate_handoff(
        org_id=org_id,
        session_id=active_session.id,
        trigger=HandoffTrigger.USER_REQUEST,
        reason="help",
        policy=policy,
    )
    await orchestrator.accept_handoff(handoff_id=package.handoff_id, org_id=org_id, user_id=uuid4())

    with pytest.raises(ValueError, match="already accepted"):
        await orchestrator.accept_handoff(
            handoff_id=package.handoff_id, org_id=org_id, user_id=uuid4()
        )


@pytest.mark.asyncio
async def test_complete_handoff_idempotent(orchestrator, active_session, handoff_settings):
    org_id = TEST_ORG_ID
    user_id = uuid4()
    policy = EscalationPolicy()

    package = await orchestrator.initiate_handoff(
        org_id=org_id,
        session_id=active_session.id,
        trigger=HandoffTrigger.USER_REQUEST,
        reason="help",
        policy=policy,
    )
    await orchestrator.accept_handoff(handoff_id=package.handoff_id, org_id=org_id, user_id=user_id)
    first = await orchestrator.complete_handoff(handoff_id=package.handoff_id, org_id=org_id)
    second = await orchestrator.complete_handoff(handoff_id=package.handoff_id, org_id=org_id)
    assert first.id == second.id
    assert first.status == HandoffStatus.COMPLETED


@pytest.mark.asyncio
async def test_to_package_builds_assignment_from_record(orchestrator):
    from voxforge.core.domain.handoff import HandoffRecord

    record = HandoffRecord(
        id=uuid4(),
        org_id=uuid4(),
        session_id=uuid4(),
        ticket_id="T-1",
        status=HandoffStatus.ASSIGNED,
        trigger=HandoffTrigger.USER_REQUEST,
        trigger_reason="test",
        conversation_summary="summary",
        replay_url="http://example.com/replay",
        assigned_to_user_id=uuid4(),
        assigned_to_email="agent@example.com",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    policy = EscalationPolicy(handoff_message="Please hold")
    package = HandoffOrchestrator._to_package(record, policy)
    assert package.assignment is not None
    assert package.assignment.assignee_email == "agent@example.com"
    assert package.handoff_message == "Please hold"
