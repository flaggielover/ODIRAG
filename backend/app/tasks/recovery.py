from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.database.session import DatabaseManager
from app.repositories.crawl import CrawlRepository
from app.tasks.celery_app import celery_app


@celery_app.task(name="odirag.crawl.recover")  # type: ignore[untyped-decorator]
def recover_crawl_tasks() -> dict[str, int]:
    return asyncio.run(_recover())


async def _recover() -> dict[str, int]:
    settings = get_settings()
    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            repository = CrawlRepository(session)
            cutoff = datetime.now(UTC) - timedelta(seconds=settings.crawl_stale_after_seconds)
            recovered, exhausted = await repository.recover_stale_tasks(
                cutoff=cutoff,
                max_recovery_attempts=settings.crawl_max_recovery_attempts,
                limit=settings.crawl_recovery_batch_size,
            )
            pending_ids = await repository.list_pending_task_ids(
                limit=settings.crawl_recovery_batch_size
            )
            queued = 0
            for task_id in pending_ids:
                celery_app.send_task("odirag.crawl.execute", args=[task_id])
                queued += 1
            return {
                "recovered": len(recovered),
                "exhausted": len(exhausted),
                "queued": queued,
            }
    finally:
        await database.dispose()
