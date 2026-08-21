"""Factory for knowledge base and ticketing provider backends."""

from voxforge.config import Settings
from voxforge.core.exceptions import ProviderError
from voxforge.core.interfaces.support import KnowledgeBaseProvider, TicketingProvider
from voxforge.infrastructure.providers.support.internal import InternalKnowledgeBaseProvider
from voxforge.infrastructure.providers.support.mock import (
    MockKnowledgeBaseProvider,
    MockTicketingProvider,
)

_REMOVED_STUBS = frozenset({"zendesk", "freshdesk"})


def create_knowledge_base_provider(settings: Settings) -> KnowledgeBaseProvider:
    provider = settings.knowledge_base_provider.lower()
    if provider == "mock":
        return MockKnowledgeBaseProvider()
    if provider == "internal":
        if not settings.knowledge_enabled:
            return MockKnowledgeBaseProvider()
        from voxforge.infrastructure.db.session import get_session_factory

        return InternalKnowledgeBaseProvider(get_session_factory(), settings)
    if provider in _REMOVED_STUBS:
        raise ProviderError(
            "factory",
            f"Knowledge base provider '{provider}' was removed (unimplemented stub). "
            "Use 'mock' or 'internal'.",
        )
    raise ProviderError("factory", f"Unknown knowledge base provider: {provider}")


def create_ticketing_provider(settings: Settings) -> TicketingProvider:
    provider = settings.ticketing_provider.lower()
    if provider == "mock":
        return MockTicketingProvider()
    if provider in _REMOVED_STUBS:
        raise ProviderError(
            "factory",
            f"Ticketing provider '{provider}' was removed (unimplemented stub). Use 'mock'.",
        )
    raise ProviderError("factory", f"Unknown ticketing provider: {provider}")
