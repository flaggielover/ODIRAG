from __future__ import annotations

import asyncio

from app.config import get_settings
from app.crawler import HttpFetcher
from app.database.session import DatabaseManager
from app.repositories.source_discovery import SourceDiscoveryRepository
from app.services.source_discovery import SourceDiscoveryService
from app.tasks.celery_app import celery_app


@celery_app.task(name="odirag.source_discovery.run")  # type: ignore[untyped-decorator]
def run_source_discovery_task(run_id: int) -> dict[str, int | str]:
    return asyncio.run(_run(run_id))


async def _run(run_id: int) -> dict[str, int | str]:
    settings = get_settings()
    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            service = SourceDiscoveryService(
                SourceDiscoveryRepository(session),
                settings,
                fetcher=HttpFetcher(
                    timeout_seconds=settings.crawler_timeout_seconds,
                    max_bytes=min(settings.max_download_bytes, 4 * 1024 * 1024),
                    max_redirects=settings.crawler_max_redirects,
                    user_agent="ODIRAG/0.1 source-discovery-worker",
                ),
            )
            run = await service.execute(run_id)
            return {"run_id": run.id, "status": run.status}
    finally:
        await database.dispose()
