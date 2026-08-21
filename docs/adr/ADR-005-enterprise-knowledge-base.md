# ADR-005: Enterprise Knowledge Base

## Status

Accepted (2026-07-10)

## Context

VoxForge provides session-scoped conversation memory via pgvector and a `knowledge_base_lookup` tool backed by mock/external support providers. Enterprise customers need:

- Org-wide document corpora (PDF, Markdown, HTML, TXT, CSV)
- Background ingestion with progress tracking
- Semantic search with citations for agent grounding
- Versioning, re-indexing, and incremental updates
- Multi-tenant isolation without vendor lock-in

The platform already has strong patterns for provider abstractions, org-scoped data access, evaluation/replay/observability integration, and pgvector usage in the memory module.

## Decision

Introduce a **Knowledge Base module** with the following architectural choices:

### 1. Storage: PostgreSQL + pgvector (not a separate vector DB)

Reuse the existing Postgres deployment with a dedicated `knowledge_chunks` table and HNSW index. This avoids operational complexity and vendor lock-in to Pinecone/Weaviate/Qdrant while leveraging proven pgvector patterns from `MemoryRepository`.

### 2. Provider ports for all swappable components

| Port | Default adapter | Alternatives |
|------|-----------------|--------------|
| `DocumentParser` | Per-format parsers in `infrastructure/knowledge/parsers/` | Custom parser via config |
| `ChunkingStrategy` | Recursive text splitter | Fixed, page, row (CSV) |
| `EmbeddingProvider` | `OpenAIEmbeddingProvider` (existing) | Local sentence-transformers, mock |
| `BlobStore` | Filesystem (dev) | S3-compatible object storage |
| `KnowledgeChunkStore` | `KnowledgeRepository` (pgvector) | — |
| `KnowledgeBaseProvider` | `InternalKnowledgeBaseProvider` | mock, zendesk, freshdesk (existing) |

No LangChain document loaders. Thin parser adapters keep dependencies minimal and testable.

### 3. Background ingestion via Postgres job queue (not Celery/ARQ)

A dedicated asyncio worker polls `knowledge_ingest_jobs` with `SELECT ... FOR UPDATE SKIP LOCKED`. This matches VoxForge's existing process model (API + optional worker containers) without introducing Redis-backed job queues or Celery broker dependencies.

Worker runs as:

```bash
python -m voxforge.infrastructure.knowledge.worker
```

### 4. Versioning model: immutable versions + active pointer

Each document upload creates a new `knowledge_document_versions` row. The parent `knowledge_documents.active_version_id` determines which version is searched. Incremental updates diff chunks by `content_hash` and only re-embed changed segments.

### 5. Citation-first retrieval

Every search result includes structured citation metadata (document title, page, heading, version, excerpt). Citations flow to:

- `knowledge_base_lookup` tool responses
- `HallucinationEvaluator.context_snippets`
- Session replay timeline events

### 6. RBAC: new `knowledge:read` / `knowledge:write` / `knowledge:delete` scopes

Members can search; admins/owners can upload and manage. All repository queries enforce `org_id` from authenticated `Principal`.

### 7. Internal KB replaces mock as default provider

`KNOWLEDGE_BASE_PROVIDER=internal` wires `InternalKnowledgeBaseProvider` to `KnowledgeSearchService`, preserving the existing `KnowledgeBaseProvider` port and `knowledge_base_lookup` tool contract.

## Alternatives Considered

| Alternative | Why not chosen |
|-------------|----------------|
| **Pinecone / Weaviate / Qdrant** | Additional infrastructure, cost, vendor lock-in; pgvector already deployed |
| **Celery + Redis job queue** | New broker dependency; Postgres `SKIP LOCKED` sufficient for ingest throughput |
| **LangChain document loaders** | Heavy abstraction; obscures parsing behavior; harder to test per-format |
| **Synchronous ingestion in API handler** | Blocks request; no progress tracking; poor UX for large PDFs |
| **Extend `memory_entries` for documents** | Conflates session turns with document chunks; different lifecycle and search scope |
| **S3-only blob storage** | Locks dev environments to cloud; filesystem adapter for local/CI |

## Consequences

**Positive**

- Enterprise KB integrates with existing evaluation, replay, and observability without new platforms
- `knowledge_base_lookup` tool works unchanged — adapter swap only
- Embedding provider abstraction allows model migration without schema changes
- Immutable versioning enables audit trails and rollback
- Incremental updates reduce embedding API costs

**Negative / trade-offs**

- pgvector HNSW tuning required at scale (millions of chunks per org)
- Single-worker ingestion may bottleneck large bulk uploads (mitigate with horizontal workers later)
- PDF parsing quality depends on `pypdf` — scanned PDFs need OCR (out of v1 scope)
- Filesystem blob store not suitable for multi-instance production (must use S3-compatible store)
- New migration adds 5 tables and HNSW index — longer migration on large deployments

## Implementation phases

| Phase | Scope | Deliverable |
|-------|-------|-------------|
| **1** | Schema, domain models, ports, parsers, chunking | Migration 010, unit tests |
| **2** | Ingestion worker, blob store, job API | Integration tests, ingest metrics |
| **3** | Search, citations, `InternalKnowledgeBaseProvider` | Search API, tool adapter |
| **4** | Agent context, hallucination integration | Pipeline hooks, replay events |
| **5** | Dashboard upload UI, benchmarks, docs | Operator UX, CI benchmarks |

## Future migration

- Hybrid search (BM25 + vector) via Postgres `tsvector`
- OCR pipeline for scanned PDFs (Tesseract or cloud OCR port)
- Collection-level RBAC and sharing
- Cross-collection federated search
- Embedding model migration tool (re-index all with new dimensions)
- Rate limiting per org on ingest API

## References

- [Knowledge Base Architecture](../architecture/knowledge-base.md)
- [ADR-005 Supplement: Retrieval Pipeline](./ADR-008-retrieval-pipeline.md)
- [Knowledge Base Benchmarks](../benchmarks/knowledge-base.md)
- [Memory Architecture](../architecture/memory.md)
- [Customer Support Tools](../architecture/customer-support-tools.md)
- [ADR-001: Programmatic Voice Pipeline Runner](./ADR-001-programmatic-voice-pipeline-runner.md)
