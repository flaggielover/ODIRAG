from types import SimpleNamespace

import pytest

from app.config import Settings
from app.schemas.source_discovery import SourceDiscoveryRunCreate
from app.tasks import source_discovery as source_discovery_tasks
from app.tasks.celery_app import celery_app, ping


def test_worker_ping_task_reports_its_real_service() -> None:
    assert ping() == {"status": "healthy", "service": "odirag-worker"}


def test_scheduler_refreshes_monitoring_alerts() -> None:
    schedule = celery_app.conf.beat_schedule["refresh-monitoring-alerts"]
    assert schedule["task"] == "odirag.monitoring.refresh_alerts"
    assert schedule["schedule"] == 300.0


def test_worker_includes_source_discovery_task_module() -> None:
    assert "app.tasks.source_discovery" in celery_app.conf.include


def test_scheduler_scans_configured_source_discovery_gaps() -> None:
    schedule = celery_app.conf.beat_schedule["scan-source-discovery-gaps"]
    assert schedule["task"] == "odirag.source_discovery.scan_gaps"
    assert schedule["schedule"] >= 300
    assert schedule["options"]["expires"] < schedule["schedule"]


@pytest.mark.asyncio
async def test_gap_scan_is_opt_in_and_skips_open_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    class UnexpectedDatabase:
        def __init__(self, _settings: Settings) -> None:
            raise AssertionError("disabled scan must not open a database")

    monkeypatch.setattr(source_discovery_tasks, "DatabaseManager", UnexpectedDatabase)
    for settings in (
        Settings(source_discovery_auto_enabled=False),
        Settings(source_discovery_auto_enabled=True, source_discovery_auto_topics=[]),
    ):
        monkeypatch.setattr(
            source_discovery_tasks, "get_settings", lambda settings=settings: settings
        )
        result = await source_discovery_tasks._scan_gaps()
        assert result["status"] == "disabled"
        assert result["created"] == 0


@pytest.mark.asyncio
async def test_gap_scan_queues_only_new_gaps(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        source_discovery_auto_enabled=True,
        source_discovery_auto_topics=["first", "already-open", "covered"],
    )
    queued: list[int] = []
    created_topics: list[str] = []

    class SessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FakeDatabase:
        def __init__(self, _settings: Settings) -> None:
            pass

        def session_factory(self) -> SessionContext:
            return SessionContext()

        async def dispose(self) -> None:
            return None

    class FakeRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def auto_run_is_due(
            self, *, topic: str, min_interval_seconds: int
        ) -> tuple[bool, str]:
            del min_interval_seconds
            return (topic != "already-open", "active_run" if topic == "already-open" else "due")

    class FakeService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def create(
            self, payload: SourceDiscoveryRunCreate, *, created_by: str
        ) -> SimpleNamespace:
            topic = payload.topic
            created_topics.append(topic)
            return SimpleNamespace(id=42, status="no_gap" if topic == "covered" else "pending")

        async def mark_queue_failure(self, _run_id: int, _error_type: str) -> None:
            raise AssertionError("queue should be available in this fixture")

    monkeypatch.setattr(source_discovery_tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(source_discovery_tasks, "DatabaseManager", FakeDatabase)
    monkeypatch.setattr(source_discovery_tasks, "SourceDiscoveryRepository", FakeRepository)
    monkeypatch.setattr(source_discovery_tasks, "SourceDiscoveryService", FakeService)
    monkeypatch.setattr(
        source_discovery_tasks,
        "build_source_discovery_fetcher",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        source_discovery_tasks.celery_app,
        "send_task",
        lambda _name, *, args: queued.extend(args),
    )

    result = await source_discovery_tasks._scan_gaps()

    assert result == {
        "status": "completed",
        "topics": 3,
        "created": 2,
        "queued": 1,
        "skipped": 1,
        "no_gap": 1,
        "failed": 0,
    }
    assert created_topics == ["first", "covered"]
    assert queued == [42]
