"""Background worker for knowledge base ingestion jobs."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from voxforge.config import get_settings
from voxforge.infrastructure.db.knowledge_repository import KnowledgeRepository
from voxforge.infrastructure.db.session import close_db, get_session_factory, init_db
from voxforge.infrastructure.knowledge.blob import create_blob_store
from voxforge.infrastructure.observability.health import KNOWLEDGE_WORKER_HEARTBEAT_KEY
from voxforge.infrastructure.observability.logging import get_logger, setup_logging
from voxforge.infrastructure.providers.embeddings.factory import create_embedding_provider
from voxforge.infrastructure.redis.client import get_redis, init_redis
from voxforge.modules.knowledge.application.ingestion_service import KnowledgeIngestionService

logger = get_logger(__name__)


async def run_worker() -> None:
    settings = get_settings()
    if not settings.knowledge_enabled:
        logger.warning("knowledge_worker_disabled")
        while True:
            await asyncio.sleep(60)

    await init_db(settings.database_url)
    await init_redis(settings.redis_url)
    factory = get_session_factory()
    blob = create_blob_store(settings.knowledge_blob_store, path=settings.knowledge_blob_path)
    poll = settings.knowledge_worker_poll_interval_sec

    logger.info("knowledge_worker_started", poll_interval_sec=poll)
    try:
        while True:
            try:
                await get_redis().set(
                    KNOWLEDGE_WORKER_HEARTBEAT_KEY,
                    str(time.time()),
                    ex=settings.knowledge_worker_heartbeat_stale_seconds * 2,
                )
            except Exception:
                logger.warning("knowledge_worker_heartbeat_failed")
            async with factory() as session:
                repo = KnowledgeRepository(session)
                job = await repo.claim_next()
                if job is None:
                    await asyncio.sleep(poll)
                    continue
                ingestion = KnowledgeIngestionService(
                    repo,
                    blob,
                    create_embedding_provider(settings),
                    settings,
                )
                try:
                    await ingestion.process_job(job.id)
                except Exception:
                    logger.exception("knowledge_worker_job_failed", job_id=str(job.id))
                await session.commit()
    finally:
        await close_db()


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
