from __future__ import annotations

import asyncio

from app.config import get_settings
from app.crawler import HttpFetcher
from app.database.session import DatabaseManager
from app.errors import AppError
from app.repositories.crawl import CrawlRepository
from app.services.crawl import CrawlService
from app.tasks.celery_app import celery_app


@celery_app.task(name="odirag.crawl.execute")  # type: ignore[untyped-decorator]
def execute_crawl_task(task_id: int) -> dict[str, int | str]:
    return asyncio.run(_execute(task_id))


@celery_app.task(name="odirag.crawl.retry_failed_url")  # type: ignore[untyped-decorator]
def retry_failed_url(failure_id: int) -> dict[str, int | str]:
    return asyncio.run(_retry_failed_url(failure_id))


async def _execute(task_id: int) -> dict[str, int | str]:
    settings = get_settings()
    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            fetcher = HttpFetcher(
                timeout_seconds=settings.crawler_timeout_seconds,
                max_bytes=settings.max_download_bytes,
                max_redirects=settings.crawler_max_redirects,
            )
            service = CrawlService(CrawlRepository(session), fetcher, settings)
            try:
                task = await service.execute(task_id)
            except AppError as exc:
                if exc.code != "TASK_ALREADY_CLAIMED":
                    raise
                task = await service.get(task_id)
            return {"task_id": task.id, "status": task.status}
    finally:
        await database.dispose()


async def _retry_failed_url(failure_id: int) -> dict[str, int | str]:
    settings = get_settings()
    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            fetcher = HttpFetcher(
                timeout_seconds=settings.crawler_timeout_seconds,
                max_bytes=settings.max_download_bytes,
                max_redirects=settings.crawler_max_redirects,
            )
            service = CrawlService(CrawlRepository(session), fetcher, settings)
            failure = await service.execute_failed_url(failure_id)
            return {"failure_id": failure.id, "status": failure.status}
    finally:
        await database.dispose()
