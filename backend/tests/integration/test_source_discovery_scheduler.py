from __future__ import annotations

from datetime import timedelta

import pytest

from app.repositories.source_discovery import SourceDiscoveryRepository
from app.tasks import source_discovery as source_discovery_tasks
from app.tasks.celery_app import celery_app


class _SharedDatabase:
    """Point the task at the application fixture's in-memory database."""

    def __init__(self, application) -> None:
        self.session_factory = application.state.database.session_factory

    async def dispose(self) -> None:
        return None


async def test_auto_scheduler_queues_once_then_honors_active_and_cooldown(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = app.state.settings.model_copy(
        update={
            "source_discovery_provider": "disabled",
            "source_discovery_auto_enabled": True,
            "source_discovery_auto_topics": ["Health"],
            "source_discovery_auto_interval_seconds": 3600,
        }
    )
    queued: list[tuple[str, list[int]]] = []

    monkeypatch.setattr(source_discovery_tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(
        source_discovery_tasks,
        "DatabaseManager",
        lambda _settings: _SharedDatabase(app),
    )
    monkeypatch.setattr(
        celery_app,
        "send_task",
        lambda name, *, args: queued.append((name, list(args))),
    )

    first = await source_discovery_tasks._scan_gaps()
    assert first == {
        "status": "completed",
        "topics": 1,
        "created": 1,
        "queued": 1,
        "skipped": 0,
        "no_gap": 0,
        "failed": 0,
    }
    assert queued[0][0] == "odirag.source_discovery.run"

    second = await source_discovery_tasks._scan_gaps()
    assert second["status"] == "completed"
    assert second["created"] == 0
    assert second["queued"] == 0
    assert second["skipped"] == 1
    assert second["failed"] == 0

    async with app.state.database.session_factory() as session:
        repository = SourceDiscoveryRepository(session)
        run = (await repository.list_runs(limit=1))[0]
        run.status = "failed"
        await repository.commit()
        due_after_interval, reason = await repository.auto_run_is_due(
            topic="health",
            min_interval_seconds=3600,
            now=run.created_at + timedelta(seconds=3601),
        )
        assert due_after_interval is True
        assert reason == "due"

    third = await source_discovery_tasks._scan_gaps()
    assert third["status"] == "completed"
    assert third["created"] == 0
    assert third["skipped"] == 1
    assert third["failed"] == 0
    assert len(queued) == 1


async def test_auto_scheduler_persists_queue_failure_without_secret_details(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = app.state.settings.model_copy(
        update={
            "source_discovery_provider": "disabled",
            "source_discovery_auto_enabled": True,
            "source_discovery_auto_topics": ["queue outage"],
        }
    )

    monkeypatch.setattr(source_discovery_tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(
        source_discovery_tasks,
        "DatabaseManager",
        lambda _settings: _SharedDatabase(app),
    )

    def fail_queue(*_args: object, **_kwargs: object) -> None:
        raise ConnectionError("broker-password-should-not-be-recorded")

    monkeypatch.setattr(celery_app, "send_task", fail_queue)

    result = await source_discovery_tasks._scan_gaps()

    assert result == {
        "status": "partial_failed",
        "topics": 1,
        "created": 1,
        "queued": 0,
        "skipped": 0,
        "no_gap": 0,
        "failed": 1,
    }
    async with app.state.database.session_factory() as session:
        repository = SourceDiscoveryRepository(session)
        run = (await repository.list_runs(limit=1))[0]
        assert run.status == "failed"
        assert run.error_message == "QUEUE_UNAVAILABLE:ConnectionError"
        events = await repository.list_events(run_id=run.id)
        queue_event = next(event for event in events if event.stage == "queue_failure")
        assert queue_event.details_json == {"error_type": "ConnectionError"}
        assert "broker-password" not in (run.error_message or "")
