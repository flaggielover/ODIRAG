from __future__ import annotations

import asyncio

import structlog

from app.config import get_settings
from app.crawler import HttpFetcher
from app.database.session import DatabaseManager
from app.repositories.source_discovery import SourceDiscoveryRepository
from app.schemas.source_discovery import SourceDiscoveryRunCreate
from app.services.source_discovery import SourceDiscoveryService
from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="odirag.source_discovery.run")  # type: ignore[untyped-decorator]
def run_source_discovery_task(run_id: int) -> dict[str, int | str]:
    return asyncio.run(_run(run_id))


@celery_app.task(name="odirag.source_discovery.scan_gaps")  # type: ignore[untyped-decorator]
def scan_source_discovery_gaps() -> dict[str, int | str]:
    """Create bounded discovery runs for explicitly configured topics.

    The task is scheduled even when disabled so a configuration change only
    requires a normal scheduler restart.  Disabled or empty-topic deployments
    return without touching the database or any external provider.
    """
    return asyncio.run(_scan_gaps())


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


async def _scan_gaps() -> dict[str, int | str]:
    settings = get_settings()
    topics = tuple(settings.source_discovery_auto_topics)
    if not settings.source_discovery_auto_enabled or not topics:
        return {
            "status": "disabled",
            "topics": len(topics),
            "created": 0,
            "queued": 0,
            "skipped": 0,
            "no_gap": 0,
            "failed": 0,
        }

    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            repository = SourceDiscoveryRepository(session)
            service = SourceDiscoveryService(
                repository,
                settings,
                fetcher=HttpFetcher(
                    timeout_seconds=settings.crawler_timeout_seconds,
                    max_bytes=min(settings.max_download_bytes, 4 * 1024 * 1024),
                    max_redirects=settings.crawler_max_redirects,
                    user_agent="ODIRAG/0.1 source-discovery-scheduler",
                ),
            )
            created = queued = skipped = no_gap = failed = 0
            for topic_index, topic in enumerate(topics):
                try:
                    normalized_topic = topic.strip()
                    due, reason = await repository.auto_run_is_due(
                        topic=normalized_topic,
                        min_interval_seconds=settings.source_discovery_auto_interval_seconds,
                    )
                    if not due:
                        skipped += 1
                        logger.info(
                            "source_discovery_auto_topic_skipped",
                            topic_index=topic_index,
                            reason=reason,
                        )
                        continue
                    run = await service.create(
                        SourceDiscoveryRunCreate(
                            topic=normalized_topic,
                            region=settings.source_discovery_auto_region,
                            organization_level=settings.source_discovery_auto_organization_level,
                            required_source_count=settings.source_discovery_auto_required_source_count,
                            required_document_count=settings.source_discovery_auto_required_document_count,
                            max_candidates=settings.source_discovery_max_candidates,
                            execution_mode="queued",
                        ),
                        created_by="source-discovery-scheduler",
                    )
                    created += 1
                    if run.status != "pending":
                        no_gap += 1
                        continue
                    try:
                        celery_app.send_task("odirag.source_discovery.run", args=[run.id])
                    except Exception as exc:
                        await service.mark_queue_failure(run.id, exc.__class__.__name__)
                        failed += 1
                        logger.warning(
                            "source_discovery_auto_queue_failed",
                            topic_index=topic_index,
                            run_id=run.id,
                            error_type=exc.__class__.__name__,
                        )
                    else:
                        queued += 1
                except Exception as exc:
                    # A malformed topic or transient database error must not
                    # prevent the remaining configured topics from being scanned.
                    await repository.rollback()
                    logger.warning(
                        "source_discovery_auto_topic_failed",
                        topic_index=topic_index,
                        error_type=exc.__class__.__name__,
                    )
                    failed += 1
            return {
                "status": "completed" if failed == 0 else "partial_failed",
                "topics": len(topics),
                "created": created,
                "queued": queued,
                "skipped": skipped,
                "no_gap": no_gap,
                "failed": failed,
            }
    finally:
        await database.dispose()
