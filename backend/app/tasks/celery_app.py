from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery(
    "odirag",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
    include=[
        "app.tasks.crawl",
        "app.tasks.monitoring",
        "app.tasks.recovery",
        "app.tasks.source_discovery",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    task_time_limit=settings.celery_task_time_limit_seconds,
    broker_transport_options={
        "visibility_timeout": settings.celery_visibility_timeout_seconds,
    },
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "refresh-monitoring-alerts": {
            "task": "odirag.monitoring.refresh_alerts",
            "schedule": 300.0,
        },
        "recover-crawl-tasks": {
            "task": "odirag.crawl.recover",
            "schedule": 60.0,
        },
        "scan-source-discovery-gaps": {
            "task": "odirag.source_discovery.scan_gaps",
            "schedule": settings.source_discovery_auto_interval_seconds,
            "options": {
                "expires": max(settings.source_discovery_auto_interval_seconds - 30, 60),
            },
        },
    },
)


@celery_app.task(name="odirag.system.ping")  # type: ignore[untyped-decorator]
def ping() -> dict[str, str]:
    """Provide a real worker readiness task without claiming domain work is configured."""
    return {"status": "healthy", "service": "odirag-worker"}
