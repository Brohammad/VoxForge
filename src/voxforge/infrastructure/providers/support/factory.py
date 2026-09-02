"""Factory for knowledge base and ticketing provider backends."""

from voxforge.config import Settings
from voxforge.core.exceptions import ProviderError
from voxforge.core.interfaces.support import KnowledgeBaseProvider, TicketingProvider
from voxforge.infrastructure.providers.support.internal import InternalKnowledgeBaseProvider
from voxforge.infrastructure.providers.support.mock import (
    MockKnowledgeBaseProvider,
    MockTicketingProvider,
)

_REMOVED_KNOWLEDGE_STUBS = frozenset({"zendesk", "freshdesk"})


def create_knowledge_base_provider(settings: Settings) -> KnowledgeBaseProvider:
    provider = settings.knowledge_base_provider.lower()
    if provider == "mock":
        return MockKnowledgeBaseProvider()
    if provider == "internal":
        if not settings.knowledge_enabled:
            return MockKnowledgeBaseProvider()
        from voxforge.infrastructure.db.session import get_session_factory

        return InternalKnowledgeBaseProvider(get_session_factory(), settings)
    if provider in _REMOVED_KNOWLEDGE_STUBS:
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
    if provider == "zendesk":
        from voxforge.infrastructure.providers.support.zendesk import (
            ZendeskTicketingProvider,
        )

        return ZendeskTicketingProvider(
            subdomain=settings.zendesk_subdomain,
            email=settings.zendesk_email,
            api_token=settings.zendesk_api_token,
            timeout_seconds=settings.tool_timeout_seconds,
        )
    if provider == "freshdesk":
        raise ProviderError(
            "factory",
            "Ticketing provider 'freshdesk' was removed (unimplemented stub). "
            "Use 'mock' or 'zendesk'.",
        )
    raise ProviderError("factory", f"Unknown ticketing provider: {provider}")
