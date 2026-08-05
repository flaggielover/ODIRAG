from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.models import CrawlTask, CrawlTaskFailure, DataLineage, Document, Source, SourceColumn
from app.repositories.crawl import CrawlRepository
from app.tasks.celery_app import celery_app


async def _seed_task(app, *, status: str = "partial_failed") -> tuple[int, int]:
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key=f"coze-task-{uuid.uuid4().hex}",
            name="Coze task source",
            domain="example.com",
            homepage_url="https://example.com/",
            crawl_provider="coze",
            coze_contract_mode="batch_crawl",
        )
        column = SourceColumn(
            source=source,
            column_key="notices",
            column_name="Notices",
            column_url="https://example.com/notices",
            request_interval_seconds=0,
        )
        task = CrawlTask(
            source_column=column,
            status=status,
            crawl_provider="coze",
            provider="coze",
            provider_contract="batch_crawl",
            contract_mode="batch_crawl",
            current_stage=status,
        )
        failure = CrawlTaskFailure(
            crawl_task=task,
            url="https://example.com/notices/failed",
            stage="detail_fetch",
            error_code="HTTP_TIMEOUT",
            error_message="timed out",
            retryable=True,
            status="failed",
        )
        session.add_all([source, column, task, failure])
        await session.commit()
        return task.id, failure.id


async def test_coze_status_never_exposes_token(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/system/coze/status", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["token_configured"] is False
    assert body["batch_workflow_configured"] is False
    configured_secret = app.state.settings.coze_api_token
    if configured_secret is not None:
        assert configured_secret.get_secret_value() not in response.text


async def test_failed_url_listing_and_retry_queue(
    app,
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_id, failure_id = await _seed_task(app)
    queued: list[int] = []

    def send_task(name: str, *, args: list[int]) -> None:
        assert name == "odirag.crawl.retry_failed_url"
        queued.extend(args)

    monkeypatch.setattr(celery_app, "send_task", send_task)
    listed = await client.get(f"/api/crawl-tasks/{task_id}/failed-urls", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["error_code"] == "HTTP_TIMEOUT"

    retried = await client.post(
        f"/api/crawl-tasks/{task_id}/failed-urls/{failure_id}/retry",
        headers=auth_headers,
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert queued == [failure_id]


async def test_cancel_active_sync_call_marks_local_only(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    task_id, _failure_id = await _seed_task(app, status="calling_coze")
    response = await client.post(f"/api/crawl-tasks/{task_id}/cancel", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["provider_status"] == "cancel_requested_local_only"
    assert "cannot be cancelled remotely" in body["provider_error_message"]


async def test_stale_cancel_cannot_overwrite_worker_stage(app) -> None:
    task_id, _failure_id = await _seed_task(app, status="calling_coze")
    async with app.state.database.session_factory() as cancel_session:
        stale_task = await cancel_session.get(CrawlTask, task_id)
        assert stale_task is not None
        await cancel_session.commit()

        async with app.state.database.session_factory() as worker_session:
            worker_repository = CrawlRepository(worker_session)
            advanced = await worker_repository.advance_task_if_status(
                task_id,
                expected_status="calling_coze",
                target_status="coze_running",
                provider_status="coze_running",
            )
            assert advanced is True

        cancelled = await CrawlRepository(cancel_session).cancel_task_if_status(
            stale_task,
            expected_status="calling_coze",
            provider_status="cancel_requested_local_only",
            provider_error_message="stale cancellation",
        )
        assert cancelled is False
        await cancel_session.refresh(stale_task)
        assert stale_task.status == "coze_running"


async def test_task_results_filter_by_decision(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    task_id, _failure_id = await _seed_task(app)
    async with app.state.database.session_factory() as session:
        task = await session.get(CrawlTask, task_id)
        assert task is not None
        column = await session.get(SourceColumn, task.source_column_id)
        assert column is not None
        document = Document(
            document_id=str(uuid.uuid4()),
            source_id=column.source_id,
            source_column_id=task.source_column_id,
            title="Accepted notice",
            source_url="https://example.com/notices/accepted",
            canonical_url="https://example.com/notices/accepted",
            content="accepted",
            word_count=8,
            rule_filter_status="accepted",
            llm_review_status="accepted",
            manual_review_status="pending",
            final_status="pending_manual_review",
            index_status="pending",
            first_crawl_time=datetime.now(UTC),
            last_crawl_time=datetime.now(UTC),
        )
        session.add(document)
        await session.flush()
        session.add(
            DataLineage(
                lineage_id=str(uuid.uuid4()),
                source_id=column.source_id,
                crawl_task_id=task.id,
                document_id=document.id,
            )
        )
        await session.commit()

    response = await client.get(
        f"/api/crawl-tasks/{task_id}/results/accepted", headers=auth_headers
    )
    assert response.status_code == 200
    assert [item["decision"] for item in response.json()] == ["accepted"]
