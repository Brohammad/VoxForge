"""PostgreSQL + pgvector persistence for enterprise knowledge base."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.core.domain.knowledge import (
    ChunkingConfig,
    ChunkMetadata,
    DocumentStatus,
    IngestJob,
    IngestJobStatus,
    IngestJobType,
    IngestStage,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    RawChunk,
    SourceType,
)
from voxforge.infrastructure.db.models import (
    KnowledgeChunkModel,
    KnowledgeCollectionModel,
    KnowledgeDocumentModel,
    KnowledgeDocumentVersionModel,
    KnowledgeIngestJobModel,
)
from voxforge.infrastructure.knowledge.util import sha256_text
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.observability.metrics import (
    duplicate_suppressed_total,
    integrity_violations_total,
)

logger = get_logger(__name__)


def _pgvector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(str(v) for v in embedding) + "]"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_collection(
        self,
        *,
        org_id: UUID,
        name: str,
        chunking_config: ChunkingConfig | None = None,
    ) -> KnowledgeCollection:
        config = chunking_config or ChunkingConfig()
        model = KnowledgeCollectionModel(
            id=uuid4(),
            org_id=org_id,
            name=name,
            embedding_dimensions=1536,
            chunking_config=config.model_dump(),
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_collection(model)

    async def list_collections(self, *, org_id: UUID) -> list[KnowledgeCollection]:
        result = await self._session.execute(
            select(KnowledgeCollectionModel)
            .where(KnowledgeCollectionModel.org_id == org_id)
            .order_by(KnowledgeCollectionModel.created_at.desc())
        )
        return [self._to_collection(m) for m in result.scalars().all()]

    async def get_collection(
        self,
        collection_id: UUID,
        *,
        org_id: UUID,
    ) -> KnowledgeCollection | None:
        result = await self._session.execute(
            select(KnowledgeCollectionModel).where(
                KnowledgeCollectionModel.id == collection_id,
                KnowledgeCollectionModel.org_id == org_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_collection(model) if model else None

    async def create_document(
        self,
        *,
        org_id: UUID,
        collection_id: UUID,
        title: str,
        source_type: SourceType,
        content_hash: str,
    ) -> KnowledgeDocument:
        now = datetime.now(UTC)
        model = KnowledgeDocumentModel(
            id=uuid4(),
            org_id=org_id,
            collection_id=collection_id,
            title=title,
            source_type=source_type.value,
            content_hash=content_hash,
            status=DocumentStatus.PENDING.value,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_document(model)

    async def get_document(
        self,
        document_id: UUID,
        *,
        org_id: UUID,
    ) -> KnowledgeDocument | None:
        result = await self._session.execute(
            select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.id == document_id,
                KnowledgeDocumentModel.org_id == org_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_document(model) if model else None

    async def list_documents(
        self,
        *,
        org_id: UUID,
        collection_id: UUID | None = None,
        limit: int = 200,
    ) -> list[KnowledgeDocument]:
        stmt = (
            select(KnowledgeDocumentModel)
            .where(KnowledgeDocumentModel.org_id == org_id)
            .order_by(KnowledgeDocumentModel.updated_at.desc())
            .limit(limit)
        )
        if collection_id is not None:
            stmt = stmt.where(KnowledgeDocumentModel.collection_id == collection_id)
        result = await self._session.execute(stmt)
        return [self._to_document(m) for m in result.scalars().all()]

    async def list_blob_paths_for_document(
        self, document_id: UUID, *, org_id: UUID
    ) -> list[str]:
        document = await self.get_document(document_id, org_id=org_id)
        if document is None:
            return []
        result = await self._session.execute(
            select(KnowledgeDocumentVersionModel.blob_path).where(
                KnowledgeDocumentVersionModel.document_id == document_id
            )
        )
        return [path for path in result.scalars().all() if path]

    async def delete_document(self, document_id: UUID, *, org_id: UUID) -> list[str]:
        blob_paths = await self.list_blob_paths_for_document(document_id, org_id=org_id)
        result = await self._session.execute(
            select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.id == document_id,
                KnowledgeDocumentModel.org_id == org_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return []
        await self._session.delete(model)
        await self._session.flush()
        return blob_paths

    async def delete_collection(
        self, collection_id: UUID, *, org_id: UUID
    ) -> tuple[int, list[str]]:
        collection = await self.get_collection(collection_id, org_id=org_id)
        if collection is None:
            return 0, []
        documents = await self.list_documents(org_id=org_id, collection_id=collection_id, limit=10_000)
        blob_paths: list[str] = []
        for document in documents:
            blob_paths.extend(
                await self.list_blob_paths_for_document(document.id, org_id=org_id)
            )
        result = await self._session.execute(
            select(KnowledgeCollectionModel).where(
                KnowledgeCollectionModel.id == collection_id,
                KnowledgeCollectionModel.org_id == org_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return 0, []
        await self._session.delete(model)
        await self._session.flush()
        return len(documents), blob_paths

    async def update_document_status(
        self,
        document_id: UUID,
        *,
        org_id: UUID,
        status: str,
    ) -> None:
        await self._session.execute(
            update(KnowledgeDocumentModel)
            .where(
                KnowledgeDocumentModel.id == document_id,
                KnowledgeDocumentModel.org_id == org_id,
            )
            .values(status=status, updated_at=datetime.now(UTC))
        )

    async def get_latest_version_number(self, document_id: UUID) -> int | None:
        result = await self._session.execute(
            select(func.max(KnowledgeDocumentVersionModel.version_number)).where(
                KnowledgeDocumentVersionModel.document_id == document_id
            )
        )
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

    async def create_version(
        self,
        *,
        document_id: UUID,
        version_number: int,
        content_hash: str,
        blob_path: str,
        metadata: dict | None = None,
    ) -> KnowledgeDocumentVersion:
        model = KnowledgeDocumentVersionModel(
            id=uuid4(),
            document_id=document_id,
            version_number=version_number,
            content_hash=content_hash,
            blob_path=blob_path,
            chunk_count=0,
            metadata_=metadata or {},
            created_at=datetime.now(UTC),
        )
        try:
            async with self._session.begin_nested():
                self._session.add(model)
                await self._session.flush()
        except IntegrityError:
            integrity_violations_total.labels(
                resource="knowledge_version", operation="create"
            ).inc()
            duplicate_suppressed_total.labels(resource="knowledge_version").inc()
            logger.info(
                "knowledge_version_duplicate_suppressed",
                document_id=str(document_id),
                version_number=version_number,
            )
            result = await self._session.execute(
                select(KnowledgeDocumentVersionModel).where(
                    KnowledgeDocumentVersionModel.document_id == document_id,
                    KnowledgeDocumentVersionModel.version_number == version_number,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise
            return self._to_version(existing)
        return self._to_version(model)

    async def set_active_version(
        self,
        document_id: UUID,
        *,
        org_id: UUID,
        version_id: UUID,
    ) -> None:
        await self._session.execute(
            update(KnowledgeDocumentModel)
            .where(
                KnowledgeDocumentModel.id == document_id,
                KnowledgeDocumentModel.org_id == org_id,
            )
            .values(active_version_id=version_id, updated_at=datetime.now(UTC))
        )

    async def get_active_version(
        self,
        document_id: UUID,
        *,
        org_id: UUID,
    ) -> KnowledgeDocumentVersion | None:
        doc = await self.get_document(document_id, org_id=org_id)
        if doc is None or doc.active_version_id is None:
            return None
        result = await self._session.execute(
            select(KnowledgeDocumentVersionModel).where(
                KnowledgeDocumentVersionModel.id == doc.active_version_id
            )
        )
        model = result.scalar_one_or_none()
        return self._to_version(model) if model else None

    async def get_version(self, version_id: UUID) -> KnowledgeDocumentVersion | None:
        result = await self._session.execute(
            select(KnowledgeDocumentVersionModel).where(
                KnowledgeDocumentVersionModel.id == version_id
            )
        )
        model = result.scalar_one_or_none()
        return self._to_version(model) if model else None

    async def update_version_chunk_count(self, version_id: UUID, count: int) -> None:
        await self._session.execute(
            update(KnowledgeDocumentVersionModel)
            .where(KnowledgeDocumentVersionModel.id == version_id)
            .values(chunk_count=count)
        )

    async def delete_chunks_by_indices(
        self,
        document_version_id: UUID,
        chunk_indices: list[int],
    ) -> int:
        if not chunk_indices:
            return 0
        result = await self._session.execute(
            select(KnowledgeChunkModel).where(
                KnowledgeChunkModel.document_version_id == document_version_id,
                KnowledgeChunkModel.chunk_index.in_(chunk_indices),
            )
        )
        models = list(result.scalars().all())
        for model in models:
            await self._session.delete(model)
        return len(models)

    async def delete_by_version(self, document_version_id: UUID) -> int:
        result = await self._session.execute(
            select(KnowledgeChunkModel).where(
                KnowledgeChunkModel.document_version_id == document_version_id
            )
        )
        models = list(result.scalars().all())
        for model in models:
            await self._session.delete(model)
        return len(models)

    async def get_chunk_hashes(self, document_version_id: UUID) -> dict[int, str]:
        result = await self._session.execute(
            select(KnowledgeChunkModel.chunk_index, KnowledgeChunkModel.content_hash).where(
                KnowledgeChunkModel.document_version_id == document_version_id
            )
        )
        return {int(row[0]): str(row[1]) for row in result.all()}

    async def upsert_chunks(
        self,
        *,
        org_id: UUID,
        document_version_id: UUID,
        chunks: list[tuple[RawChunk, list[float]]],
    ) -> int:
        count = 0
        dialect = self._session.bind.dialect.name if self._session.bind else ""
        for raw, embedding in chunks:
            chunk_id = uuid4()
            model = KnowledgeChunkModel(
                id=chunk_id,
                org_id=org_id,
                document_version_id=document_version_id,
                chunk_index=raw.chunk_index,
                content=raw.content,
                content_hash=sha256_text(raw.content),
                token_count=raw.token_count,
                metadata_=raw.metadata.model_dump(mode="json"),
                embedding=embedding,
                created_at=datetime.now(UTC),
            )
            try:
                async with self._session.begin_nested():
                    self._session.add(model)
                    await self._session.flush()
                    if dialect == "postgresql" and embedding:
                        await self._session.execute(
                            text(
                                "UPDATE knowledge_chunks SET embedding_vec = CAST(:vec AS vector) "
                                "WHERE id = :id"
                            ),
                            {"vec": _pgvector_literal(embedding), "id": str(chunk_id)},
                        )
            except IntegrityError:
                integrity_violations_total.labels(
                    resource="knowledge_chunk", operation="insert"
                ).inc()
                duplicate_suppressed_total.labels(resource="knowledge_chunk").inc()
                continue
            count += 1
        return count

    async def search_chunks(
        self,
        *,
        org_id: UUID,
        query_embedding: list[float],
        collection_id: UUID | None = None,
        limit: int,
        min_similarity: float,
    ) -> list[tuple[KnowledgeChunk, float, KnowledgeDocument, KnowledgeDocumentVersion]]:
        active_version_ids = await self._active_version_ids(org_id, collection_id)
        if not active_version_ids:
            return []

        dialect = self._session.bind.dialect.name if self._session.bind else ""
        if dialect == "postgresql":
            return await self._search_postgres(
                org_id=org_id,
                query_embedding=query_embedding,
                version_ids=active_version_ids,
                limit=limit,
                min_similarity=min_similarity,
            )
        return await self._search_sqlite(
            org_id=org_id,
            query_embedding=query_embedding,
            version_ids=active_version_ids,
            limit=limit,
            min_similarity=min_similarity,
        )

    async def enqueue(
        self,
        *,
        org_id: UUID,
        document_id: UUID,
        job_type: str,
        document_version_id: UUID | None = None,
    ) -> IngestJob:
        model = KnowledgeIngestJobModel(
            id=uuid4(),
            org_id=org_id,
            document_id=document_id,
            document_version_id=document_version_id,
            job_type=job_type,
            status=IngestJobStatus.QUEUED.value,
            progress_pct=0,
            stage=IngestStage.QUEUED.value,
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_job(model)

    async def claim_next(self) -> IngestJob | None:
        dialect = self._session.bind.dialect.name if self._session.bind else ""
        if dialect != "postgresql":
            result = await self._session.execute(
                select(KnowledgeIngestJobModel)
                .where(KnowledgeIngestJobModel.status == IngestJobStatus.QUEUED.value)
                .order_by(KnowledgeIngestJobModel.created_at.asc())
                .limit(1)
            )
        else:
            result = await self._session.execute(
                text(
                    """
                    SELECT id FROM knowledge_ingest_jobs
                    WHERE status = 'queued'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """
                )
            )
            row = result.first()
            if row is None:
                return None
            job_id = row[0]
            result = await self._session.execute(
                select(KnowledgeIngestJobModel).where(KnowledgeIngestJobModel.id == job_id)
            )

        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.status = IngestJobStatus.RUNNING.value
        model.started_at = datetime.now(UTC)
        model.stage = IngestStage.PARSING.value
        await self._session.flush()
        return self._to_job(model)

    async def update_progress(
        self,
        job_id: UUID,
        *,
        progress_pct: int,
        stage: str,
    ) -> None:
        await self._session.execute(
            update(KnowledgeIngestJobModel)
            .where(KnowledgeIngestJobModel.id == job_id)
            .values(progress_pct=progress_pct, stage=stage)
        )

    async def complete_job(self, job_id: UUID) -> None:
        await self._session.execute(
            update(KnowledgeIngestJobModel)
            .where(KnowledgeIngestJobModel.id == job_id)
            .values(
                status=IngestJobStatus.COMPLETED.value,
                progress_pct=100,
                stage=IngestStage.COMPLETED.value,
                completed_at=datetime.now(UTC),
            )
        )

    async def fail_job(self, job_id: UUID, *, error_message: str) -> None:
        await self._session.execute(
            update(KnowledgeIngestJobModel)
            .where(KnowledgeIngestJobModel.id == job_id)
            .values(
                status=IngestJobStatus.FAILED.value,
                error_message=error_message,
                completed_at=datetime.now(UTC),
            )
        )

    async def get_job(self, job_id: UUID, *, org_id: UUID) -> IngestJob | None:
        result = await self._session.execute(
            select(KnowledgeIngestJobModel).where(
                KnowledgeIngestJobModel.id == job_id,
                KnowledgeIngestJobModel.org_id == org_id,
            )
        )
        model = result.scalar_one_or_none()
        return self._to_job(model) if model else None

    async def get_job_by_id(self, job_id: UUID) -> IngestJob | None:
        result = await self._session.execute(
            select(KnowledgeIngestJobModel).where(KnowledgeIngestJobModel.id == job_id)
        )
        model = result.scalar_one_or_none()
        return self._to_job(model) if model else None

    async def list_jobs_for_document(
        self,
        document_id: UUID,
        *,
        org_id: UUID,
    ) -> list[IngestJob]:
        result = await self._session.execute(
            select(KnowledgeIngestJobModel)
            .where(
                KnowledgeIngestJobModel.document_id == document_id,
                KnowledgeIngestJobModel.org_id == org_id,
            )
            .order_by(KnowledgeIngestJobModel.created_at.desc())
        )
        return [self._to_job(m) for m in result.scalars().all()]

    async def _active_version_ids(self, org_id: UUID, collection_id: UUID | None) -> list[UUID]:
        stmt = select(KnowledgeDocumentModel.active_version_id).where(
            KnowledgeDocumentModel.org_id == org_id,
            KnowledgeDocumentModel.status == DocumentStatus.READY.value,
            KnowledgeDocumentModel.active_version_id.is_not(None),
        )
        if collection_id is not None:
            stmt = stmt.where(KnowledgeDocumentModel.collection_id == collection_id)
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all() if row[0] is not None]

    async def _search_postgres(
        self,
        *,
        org_id: UUID,
        query_embedding: list[float],
        version_ids: list[UUID],
        limit: int,
        min_similarity: float,
    ) -> list[tuple[KnowledgeChunk, float, KnowledgeDocument, KnowledgeDocumentVersion]]:
        query_vec = _pgvector_literal(query_embedding)
        version_list = ",".join(f"'{vid}'" for vid in version_ids)
        result = await self._session.execute(
            text(
                f"""
                SELECT c.id, c.org_id, c.document_version_id, c.chunk_index, c.content,
                       c.content_hash, c.token_count, c.metadata, c.created_at,
                       1 - (c.embedding_vec <=> CAST(:query_vec AS vector)) AS similarity,
                       d.id, d.org_id, d.collection_id, d.title, d.source_type,
                       d.content_hash, d.active_version_id, d.status, d.created_at, d.updated_at,
                       v.id, v.document_id, v.version_number, v.content_hash, v.blob_path,
                       v.chunk_count, v.metadata, v.created_at
                FROM knowledge_chunks c
                JOIN knowledge_document_versions v ON v.id = c.document_version_id
                JOIN knowledge_documents d ON d.id = v.document_id
                WHERE c.org_id = :org_id
                  AND c.document_version_id IN ({version_list})
                  AND c.embedding_vec IS NOT NULL
                ORDER BY c.embedding_vec <=> CAST(:query_vec AS vector)
                LIMIT :limit
                """
            ),
            {"org_id": str(org_id), "query_vec": query_vec, "limit": limit * 3},
        )
        return self._rows_to_scored(result.all(), min_similarity, limit)

    async def _search_sqlite(
        self,
        *,
        org_id: UUID,
        query_embedding: list[float],
        version_ids: list[UUID],
        limit: int,
        min_similarity: float,
    ) -> list[tuple[KnowledgeChunk, float, KnowledgeDocument, KnowledgeDocumentVersion]]:
        result = await self._session.execute(
            select(KnowledgeChunkModel).where(
                KnowledgeChunkModel.org_id == org_id,
                KnowledgeChunkModel.document_version_id.in_(version_ids),
            )
        )
        scored: list[tuple[KnowledgeChunk, float, KnowledgeDocument, KnowledgeDocumentVersion]] = []
        for chunk_model in result.scalars().all():
            if not chunk_model.embedding:
                continue
            similarity = _cosine_similarity(query_embedding, chunk_model.embedding)
            if similarity < min_similarity:
                continue
            version_model = await self._session.get(
                KnowledgeDocumentVersionModel, chunk_model.document_version_id
            )
            doc_model = (
                await self._session.get(KnowledgeDocumentModel, version_model.document_id)
                if version_model
                else None
            )
            if version_model is None or doc_model is None:
                continue
            scored.append(
                (
                    self._to_chunk(chunk_model),
                    similarity,
                    self._to_document(doc_model),
                    self._to_version(version_model),
                )
            )
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    def _rows_to_scored(self, rows, min_similarity: float, limit: int):
        scored = []
        for row in rows:
            similarity = float(row[9])
            if similarity < min_similarity:
                continue
            chunk = KnowledgeChunk(
                id=row[0],
                org_id=row[1],
                document_version_id=row[2],
                chunk_index=row[3],
                content=row[4],
                content_hash=row[5],
                token_count=row[6],
                metadata=ChunkMetadata.model_validate(row[7] or {}),
                created_at=row[8],
            )
            document = KnowledgeDocument(
                id=row[10],
                org_id=row[11],
                collection_id=row[12],
                title=row[13],
                source_type=SourceType(row[14]),
                content_hash=row[15],
                active_version_id=row[16],
                status=DocumentStatus(row[17]),
                created_at=row[18],
                updated_at=row[19],
            )
            version = KnowledgeDocumentVersion(
                id=row[20],
                document_id=row[21],
                version_number=row[22],
                content_hash=row[23],
                blob_path=row[24],
                chunk_count=row[25],
                metadata=row[26] or {},
                created_at=row[27],
            )
            scored.append((chunk, similarity, document, version))
        return scored[:limit]

    @staticmethod
    def _to_collection(model: KnowledgeCollectionModel) -> KnowledgeCollection:
        return KnowledgeCollection(
            id=model.id,
            org_id=model.org_id,
            name=model.name,
            embedding_dimensions=model.embedding_dimensions,
            chunking_config=ChunkingConfig.model_validate(model.chunking_config or {}),
            created_at=model.created_at,
        )

    @staticmethod
    def _to_document(model: KnowledgeDocumentModel) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=model.id,
            org_id=model.org_id,
            collection_id=model.collection_id,
            title=model.title,
            source_type=SourceType(model.source_type),
            content_hash=model.content_hash,
            active_version_id=model.active_version_id,
            status=DocumentStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_version(model: KnowledgeDocumentVersionModel) -> KnowledgeDocumentVersion:
        return KnowledgeDocumentVersion(
            id=model.id,
            document_id=model.document_id,
            version_number=model.version_number,
            content_hash=model.content_hash,
            blob_path=model.blob_path,
            chunk_count=model.chunk_count,
            metadata=model.metadata_ or {},
            created_at=model.created_at,
        )

    @staticmethod
    def _to_chunk(model: KnowledgeChunkModel) -> KnowledgeChunk:
        return KnowledgeChunk(
            id=model.id,
            org_id=model.org_id,
            document_version_id=model.document_version_id,
            chunk_index=model.chunk_index,
            content=model.content,
            content_hash=model.content_hash,
            token_count=model.token_count,
            metadata=ChunkMetadata.model_validate(model.metadata_ or {}),
            created_at=model.created_at,
        )

    @staticmethod
    def _to_job(model: KnowledgeIngestJobModel) -> IngestJob:
        return IngestJob(
            id=model.id,
            org_id=model.org_id,
            document_id=model.document_id,
            document_version_id=model.document_version_id,
            job_type=IngestJobType(model.job_type),
            status=IngestJobStatus(model.status),
            progress_pct=model.progress_pct,
            stage=IngestStage(model.stage) if model.stage else None,
            error_message=model.error_message,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
        )
