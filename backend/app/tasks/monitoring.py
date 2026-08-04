from __future__ import annotations

import asyncio
from collections import Counter

from app.config import get_settings
from app.database.session import DatabaseManager
from app.repositories.observability import ObservabilityRepository
from app.services.health import HealthService
from app.services.observability import MonitoringService
from app.tasks.celery_app import celery_app


@celery_app.task(name="odirag.monitoring.refresh_alerts")  # type: ignore[untyped-decorator]
def refresh_monitoring_alerts() -> dict[str, object]:
    return asyncio.run(_refresh())


async def _refresh() -> dict[str, object]:
    settings = get_settings()
    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            service = MonitoringService(ObservabilityRepository(session), settings)
            metrics = await service.metrics()
            health = await HealthService(session, settings).check()
            alerts = await service.refresh_alerts(metrics, health)
            status_counts = Counter(alert.status for alert in alerts)
            return {
                "status": "completed",
                "alert_count": len(alerts),
                "alerts_by_status": dict(status_counts),
            }
    finally:
        await database.dispose()
