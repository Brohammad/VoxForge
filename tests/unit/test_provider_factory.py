"""Tests for provider factory and mock providers."""

import pytest

from voxforge.config import Settings
from voxforge.core.exceptions import ProviderError
from voxforge.infrastructure.providers.factory import (
    create_llm_provider,
    create_stt_provider,
    create_tts_provider,
)
from voxforge.infrastructure.providers.mock import MockLLMProvider, MockSTTProvider, MockTTSProvider


def test_factory_creates_mock_providers():
    settings = Settings(stt_provider="mock", llm_provider="mock", tts_provider="mock")
    assert isinstance(create_stt_provider(settings), MockSTTProvider)
    assert isinstance(create_llm_provider(settings), MockLLMProvider)
    assert isinstance(create_tts_provider(settings), MockTTSProvider)


def test_factory_unknown_provider_raises():
    with pytest.raises(ProviderError):
        create_stt_provider(Settings(stt_provider="unknown"))


@pytest.mark.asyncio
async def test_mock_llm_streams_response():
    from voxforge.core.domain.entities import MessageRole
    from voxforge.modules.memory.application.context_builder import ChatMessageLike

    llm = MockLLMProvider()
    messages = [ChatMessageLike(role=MessageRole.USER, content="Hello")]
    tokens = [event.text async for event in llm.generate_stream(messages, model="mock")]
    assert any("Mock response" in t for t in tokens)


@pytest.mark.asyncio
async def test_mock_llm_billing_contact_script():
    from voxforge.core.domain.entities import MessageRole
    from voxforge.modules.memory.application.context_builder import ChatMessageLike

    llm = MockLLMProvider()
    messages = [
        ChatMessageLike(
            role=MessageRole.USER,
            content="Hi, I need help changing the billing contact on my account.",
        )
    ]
    tokens = [event.text async for event in llm.generate_stream(messages, model="mock")]
    assert any("updated the billing contact" in t for t in tokens)


@pytest.mark.asyncio
async def test_mock_llm_refund_script():
    from voxforge.core.domain.entities import MessageRole
    from voxforge.modules.memory.application.context_builder import ChatMessageLike

    llm = MockLLMProvider()
    messages = [ChatMessageLike(role=MessageRole.USER, content="What is your refund policy?")]
    tokens = [event.text async for event in llm.generate_stream(messages, model="mock")]
    assert any("30 days" in t for t in tokens)
