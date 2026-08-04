from app.tasks.celery_app import celery_app, ping


def test_worker_ping_task_reports_its_real_service() -> None:
    assert ping() == {"status": "healthy", "service": "odirag-worker"}


def test_scheduler_refreshes_monitoring_alerts() -> None:
    schedule = celery_app.conf.beat_schedule["refresh-monitoring-alerts"]
    assert schedule["task"] == "odirag.monitoring.refresh_alerts"
    assert schedule["schedule"] == 300.0


def test_worker_includes_source_discovery_task_module() -> None:
    assert "app.tasks.source_discovery" in celery_app.conf.include
