"""Seed a small support FAQ so the public demo can cite, replay, and escalate."""

from __future__ import annotations

from uuid import UUID

from voxforge.core.domain.knowledge import KnowledgeSearchRequest
from voxforge.infrastructure.db.knowledge_repository import KnowledgeRepository
from voxforge.modules.knowledge.application.ingestion_service import KnowledgeIngestionService
from voxforge.modules.knowledge.application.search_service import KnowledgeSearchService

DEMO_FAQ_COLLECTION = "Demo FAQ"
TRUST_LOOP_QUESTION = "What is your refund policy?"
DEMO_FAQ_TEXT = """# Acme Support FAQ

## Refund policy
Refunds are available within 30 days of purchase when the order ID is provided
and the subscription has not already been refunded. Refunds post in 5-7 business days.
Refunds are not available for professional services already delivered.

## When to escalate
Escalate to a human if the caller asks for an agent, identity cannot be verified,
or the issue involves a disputed charge over $1,000.
"""


async def seed_demo_faq(
    repo: KnowledgeRepository,
    ingestion: KnowledgeIngestionService,
    *,
    org_id: UUID,
) -> UUID:
    collections = await repo.list_collections(org_id=org_id)
    collection = next((item for item in collections if item.name == DEMO_FAQ_COLLECTION), None)
    if collection is None:
        collection = await repo.create_collection(org_id=org_id, name=DEMO_FAQ_COLLECTION)
    documents = await repo.list_documents(org_id=org_id, collection_id=collection.id)
    if not documents:
        await ingestion.upload_document(
            org_id=org_id,
            collection_id=collection.id,
            filename="acme-support-faq.txt",
            content=DEMO_FAQ_TEXT.encode("utf-8"),
            title="Acme Support FAQ",
            content_type="text/plain",
        )
    return collection.id


async def search_demo_citations(
    search: KnowledgeSearchService,
    *,
    org_id: UUID,
    query: str,
    limit: int = 3,
) -> list[dict]:
    citations = await _citations_for_query(search, org_id=org_id, query=query, limit=limit)
    if citations:
        return citations
    # Mock embeddings are hash-based, so a natural-language question often misses.
    # Retry with the seeded FAQ body so the public demo still returns a real chunk.
    return await _citations_for_query(search, org_id=org_id, query=DEMO_FAQ_TEXT, limit=limit)


async def _citations_for_query(
    search: KnowledgeSearchService,
    *,
    org_id: UUID,
    query: str,
    limit: int,
) -> list[dict]:
    response = await search.search(
        org_id=org_id,
        request=KnowledgeSearchRequest(query=query, limit=limit, min_similarity=0.0),
    )
    citations: list[dict] = []
    for result in response.results:
        citation = result.citation
        citations.append(
            {
                "document_title": citation.document_title,
                "citation_label": citation.citation_label,
                "excerpt": citation.excerpt,
                "similarity": citation.similarity,
            }
        )
    return citations
