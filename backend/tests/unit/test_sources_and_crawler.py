from __future__ import annotations

import httpx
import pytest

from app.crawler.state import CrawlTaskStateMachine, InvalidTaskTransitionError
from app.crawler.storage import safe_filename
from app.crawler.urls import normalize_url
from app.models import CrawlTask
from app.repositories.sources import SourceRepository
from app.schemas.source import SourceCreate
from app.services.sources import SourceService


async def _public_addresses(_hostname: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


def test_url_normalization_resolves_relative_and_removes_tracking() -> None:
    assert (
        normalize_url(
            "../policy?id=2&utm_source=test&id=1#section", base_url="HTTPS://EXAMPLE.GOV/list/"
        )
        == "https://example.gov/policy?id=1&id=2"
    )


def test_safe_filename_removes_path_segments() -> None:
    result = safe_filename("../../政策 文件.pdf")
    assert "/" not in result and "\\" not in result
    assert result.endswith(".pdf")


def test_crawl_task_state_machine_rejects_invalid_transition() -> None:
    task = CrawlTask(source_column_id=1, status="pending")
    state = CrawlTaskStateMachine()
    state.transition(task, "running")
    assert task.started_at is not None
    with pytest.raises(InvalidTaskTransitionError):
        state.transition(task, "pending")
    state.transition(task, "completed")
    assert task.finished_at is not None


def test_crawl_task_retry_clears_previous_provider_progress() -> None:
    task = CrawlTask(
        source_column_id=1,
        status="failed",
        current_stage="failed",
        accepted_count=3,
        rejected_count=2,
        pending_review_count=1,
        provider_status="failed",
        provider_error_code="COZE_TIMEOUT",
        provider_error_message="timed out",
        provider_task_id="remote-id",
        coze_execution_id="execution-id",
    )

    CrawlTaskStateMachine().transition(task, "pending")

    assert task.current_stage == "pending"
    assert (task.accepted_count, task.rejected_count, task.pending_review_count) == (0, 0, 0)
    assert task.provider_status is None
    assert task.provider_error_code is None
    assert task.provider_task_id is None
    assert task.coze_execution_id is None


async def test_source_service_connectivity_uses_real_http_response(app) -> None:
    async with app.state.database.session_factory() as session:
        source = await SourceService(SourceRepository(session)).create(
            SourceCreate(
                source_key="connectivity",
                name="Connectivity fixture",
                domain="example.gov",
                homepage_url="https://example.gov/",
            )
        )
        transport = httpx.MockTransport(lambda request: httpx.Response(204, request=request))
        async with httpx.AsyncClient(transport=transport) as client:
            result = await SourceService(
                SourceRepository(session),
                client=client,
                resolver=_public_addresses,
            ).test(source.id)
        assert result.reachable
        assert result.status_code == 204


async def test_source_connectivity_rejects_private_targets_before_http(app) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, request=request)

    async with app.state.database.session_factory() as session:
        source = await SourceService(SourceRepository(session)).create(
            SourceCreate(
                source_key="private-connectivity",
                name="Private connectivity fixture",
                domain="private.example",
                homepage_url="http://127.0.0.1/internal",
            )
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await SourceService(SourceRepository(session), client=client).test(source.id)

    assert not result.reachable
    assert result.error_type == "UnsafeUrlError"
    assert not called


async def test_source_crud_api(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post(
        "/api/sources",
        headers=auth_headers,
        json={
            "source_key": "fixture-api",
            "name": "Fixture source",
            "domain": "fixture.gov",
            "homepage_url": "https://fixture.gov/",
            "region": "四川",
            "columns": [
                {
                    "column_key": "policies",
                    "column_name": "政策",
                    "column_url": "https://fixture.gov/list.html",
                    "max_pages": 2,
                    "request_interval_seconds": 0,
                    "selectors_json": {
                        "list_link": "a.item",
                        "title": "h1",
                        "content": "article",
                    },
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]
    assert created.json()["columns"][0]["column_key"] == "policies"
    listed = await client.get("/api/sources", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["id"] == source_id for item in listed.json())
    updated = await client.put(
        f"/api/sources/{source_id}",
        headers=auth_headers,
        json={"priority": 10, "name": "Updated fixture"},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == 10
    deleted = await client.delete(f"/api/sources/{source_id}", headers=auth_headers)
    assert deleted.status_code == 204


async def test_crawl_queue_failure_is_persisted_and_retryable(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = await client.post(
        "/api/sources",
        headers=auth_headers,
        json={
            "source_key": "queue-failure-source",
            "name": "Queue failure source",
            "domain": "queue-failure.gov",
            "homepage_url": "https://queue-failure.gov/",
            "columns": [
                {
                    "column_key": "policies",
                    "column_name": "Policies",
                    "column_url": "https://queue-failure.gov/policies",
                    "request_interval_seconds": 0,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    column_id = created.json()["columns"][0]["id"]

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr("app.api.routes.crawl_tasks.celery_app.send_task", unavailable)
    queued = await client.post(
        "/api/crawl-tasks",
        headers=auth_headers,
        json={"source_column_id": column_id, "execution_mode": "queued"},
    )
    assert queued.status_code == 503, queued.text
    task_id = queued.json()["error"]["details"]["task_id"]

    failed = await client.get(f"/api/crawl-tasks/{task_id}", headers=auth_headers)
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["failed_count"] == 1
    assert failed.json()["error_message"] == "TASK_QUEUE_UNAVAILABLE:RuntimeError"
    assert failed.json()["provider_error_code"] == "TASK_QUEUE_UNAVAILABLE"
    assert failed.json()["provider_error_message"] == (
        "Crawl task could not be queued: RuntimeError"
    )

    sent: list[int] = []

    def available(_name: str, *, args: list[int]) -> None:
        sent.extend(args)

    monkeypatch.setattr("app.api.routes.crawl_tasks.celery_app.send_task", available)
    retried = await client.post(f"/api/crawl-tasks/{task_id}/retry", headers=auth_headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "pending"
    assert retried.json()["retry_count"] == 1
    assert sent == [task_id]


async def test_inline_crawl_unsafe_url_returns_structured_error(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post(
        "/api/sources",
        headers=auth_headers,
        json={
            "source_key": "unsafe-inline-source",
            "name": "Unsafe inline source",
            "domain": "localhost",
            "homepage_url": "http://localhost/",
            "columns": [
                {
                    "column_key": "internal",
                    "column_name": "Internal",
                    "column_url": "http://localhost/internal",
                    "request_interval_seconds": 0,
                    "selectors_json": {
                        "list_link": "a[href]",
                        "title": "h1",
                        "content": "article",
                    },
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    column_id = created.json()["columns"][0]["id"]

    response = await client.post(
        "/api/crawl-tasks",
        headers=auth_headers,
        json={"source_column_id": column_id, "execution_mode": "inline"},
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "CRAWL_SOURCE_UNSAFE"
    task_id = response.json()["error"]["details"]["task_id"]
    failed = await client.get(f"/api/crawl-tasks/{task_id}", headers=auth_headers)
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["error_message"] == "UnsafeUrlError"
