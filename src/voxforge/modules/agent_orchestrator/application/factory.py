from typing import TYPE_CHECKING

from voxforge.config import Settings
from voxforge.core.interfaces.response_generator import ResponseGenerator
from voxforge.infrastructure.providers.llm.openai import OpenAILLMProvider
from voxforge.modules.agent_orchestrator.application.service import AgentOrchestrator
from voxforge.modules.conversation.application.engine import ConversationEngine

if TYPE_CHECKING:
    from voxforge.modules.knowledge.application.context_builder import KnowledgeContextBuilder
    from voxforge.modules.mcp_tool_router.application.router import ToolRouter
    from voxforge.modules.memory.application.service import MemoryService


def create_response_generator(
    settings: Settings,
    llm: OpenAILLMProvider | None = None,
    memory_service: "MemoryService | None" = None,
    tool_router: "ToolRouter | None" = None,
    knowledge_context_builder: "KnowledgeContextBuilder | None" = None,
) -> ResponseGenerator:
    if settings.orchestrator_mode == "multi_agent":
        return AgentOrchestrator(
            settings,
            memory_service=memory_service,
            tool_router=tool_router,
            knowledge_context_builder=knowledge_context_builder,
            llm=llm,
        )
    if llm is None:
        llm = OpenAILLMProvider(settings.openai_api_key)
    return ConversationEngine(
        llm,
        settings,
        memory_service=memory_service,
        knowledge_context_builder=knowledge_context_builder,
    )
