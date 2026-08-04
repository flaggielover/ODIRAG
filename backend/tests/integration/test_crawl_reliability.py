from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.crawler.fetcher import FetchResponse
from app.repositories.crawl import CrawlRepository
from app.repositories.sources import SourceRepository
from app.schemas.crawl import CrawlTaskCreate
from app.schemas.source import SourceColumnCreate, SourceCreate
from app.services.crawl import CrawlService
from app.services.sources import SourceService
from app.tasks.celery_app import celery_app


class UnusedFetcher:
    async def fetch(self, _url: str) -> FetchResponse:
        raise AssertionError("fetch should not be called")


async def _create_task(app) -> int:
    async with app.state.database.session_factory() as session:
        source = await SourceService(SourceRepository(session)).create(
            SourceCreate(
                source_key=f"reliability-{uuid.uuid4().hex}",
                name="Reliability fixture",
                domain="reliability.example",
                homepage_url="https://reliability.example/",
                columns=[
                    SourceColumnCreate(
                        column_key="policies",
                        column_name="Policies",
                        column_url="https://reliability.example/policies",
                        request_interval_seconds=0,
                    )
                ],
            )
        )
        service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            app.state.settings,
        )
        task = await service.create(CrawlTaskCreate(source_column_id=source.columns[0].id))
        return task.id


async def test_crawl_task_claim_is_atomic_and_stale_tasks_recover(app) -> None:
    task_id = await _create_task(app)
    async with app.state.database.session_factory() as session:
        repository = CrawlRepository(session)
        claimed = await repository.claim_task(task_id)
        assert claimed is not None
        assert claimed.status == "running"
        assert await repository.claim_task(task_id) is None

        claimed.started_at = datetime.now(UTC) - timedelta(hours=2)
        claimed.discovered_count = 9
        claimed.fetched_count = 8
        claimed.success_count = 7
        claimed.accepted_count = 4
        claimed.rejected_count = 2
        claimed.pending_review_count = 1
        claimed.completed_at = datetime.now(UTC)
        await repository.save_task(claimed)

        recovered, exhausted = await repository.recover_stale_tasks(
            cutoff=datetime.now(UTC) - timedelta(minutes=30),
            max_recovery_attempts=3,
            limit=10,
        )
        assert recovered == [task_id]
        assert exhausted == []
        task = await repository.get_task(task_id)
        assert task is not None
        assert task.status == "pending"
        assert task.retry_count == 1
        assert task.discovered_count == 0
        assert task.fetched_count == 0
        assert task.success_count == 0
        assert task.accepted_count == 0
        assert task.rejected_count == 0
        assert task.pending_review_count == 0
        assert task.completed_at is None

        claimed_again = await repository.claim_task(task_id)
        assert claimed_again is not None
        claimed_again.started_at = datetime.now(UTC) - timedelta(hours=2)
        claimed_again.retry_count = 3
        await repository.save_task(claimed_again)
        recovered, exhausted = await repository.recover_stale_tasks(
            cutoff=datetime.now(UTC) - timedelta(minutes=30),
            max_recovery_attempts=3,
            limit=10,
        )
        assert recovered == []
        assert exhausted == [task_id]
        task = await repository.get_task(task_id)
        assert task is not None
        assert task.status == "failed"
        assert task.current_stage == "failed"
        assert task.completed_at is not None
        assert task.error_message == "WORKER_LOST_MAX_RECOVERIES"


async def test_retry_endpoint_requeues_the_task(
    app,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id = await _create_task(app)
    async with app.state.database.session_factory() as session:
        repository = CrawlRepository(session)
        task = await repository.get_task(task_id)
        assert task is not None
        task.status = "failed"
        task.started_at = datetime.now(UTC) - timedelta(minutes=1)
        task.finished_at = datetime.now(UTC)
        await repository.save_task(task)

    queued: list[tuple[str, list[int]]] = []

    def send_task(name: str, *, args: list[int]) -> None:
        queued.append((name, args))

    monkeypatch.setattr(celery_app, "send_task", send_task)
    response = await client.post(f"/api/crawl-tasks/{task_id}/retry", headers=auth_headers)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    assert response.json()["retry_count"] == 1
    assert queued == [("odirag.crawl.execute", [task_id])]
