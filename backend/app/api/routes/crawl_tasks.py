from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.config import Settings
from app.crawler import HttpFetcher, UnsafeUrlError
from app.dependencies import (
    AdminUser,
    DatabaseSession,
    get_app_settings,
    get_application_runtime,
)
from app.errors import AppError
from app.models import CrawlTask
from app.repositories.crawl import CrawlRepository
from app.runtime import ApplicationRuntime
from app.schemas.crawl import (
    CozeInvocationResponse,
    CrawlTaskAcceptanceSummaryResponse,
    CrawlTaskCreate,
    CrawlTaskFailureResponse,
    CrawlTaskResponse,
    CrawlTaskResultResponse,
)
from app.services.crawl import CrawlService
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/crawl-tasks", tags=["crawling"])


async def _queue_task(task_id: int, service: CrawlService, *, mark_queued: bool = True) -> None:
    try:
        celery_app.send_task("odirag.crawl.execute", args=[task_id])
        if mark_queued:
            await service.mark_queued(task_id)
    except Exception as exc:
        await service.mark_queue_failure(task_id, error_type=exc.__class__.__name__)
        raise AppError(
            "TASK_QUEUE_UNAVAILABLE",
            "Crawl task was persisted but could not be queued",
            status_code=503,
            details={"task_id": task_id, "error_type": exc.__class__.__name__},
        ) from exc


def get_crawl_service(
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> CrawlService:
    return CrawlService(
        CrawlRepository(session),
        HttpFetcher(
            timeout_seconds=settings.crawler_timeout_seconds,
            max_bytes=settings.max_download_bytes,
            max_redirects=settings.crawler_max_redirects,
        ),
        settings,
    )


CrawlServiceDependency = Annotated[CrawlService, Depends(get_crawl_service)]


async def _execute_inline(task_id: int, service: CrawlService) -> CrawlTask:
    try:
        return await service.execute(task_id)
    except UnsafeUrlError as exc:
        raise AppError(
            "CRAWL_SOURCE_UNSAFE",
            "The source URL failed public-network safety validation",
            status_code=422,
            details={"task_id": task_id, "error_type": exc.__class__.__name__},
        ) from exc


@router.post("", response_model=CrawlTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_crawl_task(
    payload: CrawlTaskCreate,
    _admin: AdminUser,
    service: CrawlServiceDependency,
) -> CrawlTaskResponse:
    task = await service.create(payload)
    if payload.execution_mode == "inline":
        task = await _execute_inline(task.id, service)
    else:
        await _queue_task(task.id, service)
    return CrawlTaskResponse.model_validate(task)


@router.get("", response_model=list[CrawlTaskResponse])
async def list_crawl_tasks(
    _admin: AdminUser,
    service: CrawlServiceDependency,
    task_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[CrawlTaskResponse]:
    return [
        CrawlTaskResponse.model_validate(task) for task in await service.list(status=task_status)
    ]


@router.get("/{task_id}", response_model=CrawlTaskResponse)
async def get_crawl_task(
    task_id: int, _admin: AdminUser, service: CrawlServiceDependency
) -> CrawlTaskResponse:
    return CrawlTaskResponse.model_validate(await service.get(task_id))


@router.get(
    "/{task_id}/acceptance-summary",
    response_model=CrawlTaskAcceptanceSummaryResponse,
)
async def get_crawl_task_acceptance_summary(
    task_id: int,
    _admin: AdminUser,
    service: CrawlServiceDependency,
    runtime: Annotated[ApplicationRuntime, Depends(get_application_runtime)],
) -> CrawlTaskAcceptanceSummaryResponse:
    await service.get(task_id)
    database_ids, document_ids, chunk_count = await service.repository.acceptance_document_ids(
        task_id
    )
    qdrant_point_count = 0
    for document_id in document_ids:
        qdrant_point_count += await runtime.vector_store.count({"document_id": document_id})
    return CrawlTaskAcceptanceSummaryResponse(
        crawl_task_id=task_id,
        database_document_count=len(database_ids),
        chunk_count=chunk_count,
        qdrant_point_count=qdrant_point_count,
    )


@router.get("/{task_id}/invocations", response_model=list[CozeInvocationResponse])
async def list_coze_invocations(
    task_id: int,
    _admin: AdminUser,
    service: CrawlServiceDependency,
) -> list[CozeInvocationResponse]:
    await service.get(task_id)
    return [
        CozeInvocationResponse.model_validate(item)
        for item in await service.repository.list_coze_invocations(task_id)
    ]


@router.get("/{task_id}/failed-urls", response_model=list[CrawlTaskFailureResponse])
async def list_failed_urls(
    task_id: int,
    _admin: AdminUser,
    service: CrawlServiceDependency,
) -> list[CrawlTaskFailureResponse]:
    await service.get(task_id)
    return [
        CrawlTaskFailureResponse.model_validate(item)
        for item in await service.repository.list_failures(task_id)
    ]


@router.post(
    "/{task_id}/failed-urls/{failure_id}/retry",
    response_model=CrawlTaskFailureResponse,
)
async def retry_failed_url(
    task_id: int,
    failure_id: int,
    _admin: AdminUser,
    service: CrawlServiceDependency,
) -> CrawlTaskFailureResponse:
    failure = await service.queue_failure_retry(task_id, failure_id)
    try:
        celery_app.send_task("odirag.crawl.retry_failed_url", args=[failure_id])
    except Exception as exc:
        await service.mark_failure_queue_error(failure_id, exc.__class__.__name__)
        raise AppError(
            "TASK_QUEUE_UNAVAILABLE",
            "Failed URL retry could not be queued",
            status_code=503,
            details={"task_id": task_id, "failure_id": failure_id},
        ) from exc
    return CrawlTaskFailureResponse.model_validate(failure)


@router.get("/{task_id}/results", response_model=list[CrawlTaskResultResponse])
async def list_task_results(
    task_id: int,
    _admin: AdminUser,
    service: CrawlServiceDependency,
    decision: Annotated[str | None, Query()] = None,
) -> list[CrawlTaskResultResponse]:
    await service.get(task_id)
    documents = await service.repository.list_task_documents(task_id)
    responses: list[CrawlTaskResultResponse] = []
    for document in documents:
        document_decision = document.llm_review_status
        if decision is not None and document_decision != decision:
            continue
        reviews = sorted(document.reviews, key=lambda review: (review.created_at, review.id))
        latest = reviews[-1] if reviews else None
        responses.append(
            CrawlTaskResultResponse(
                id=document.id,
                document_id=document.document_id,
                title=document.title,
                source_url=document.source_url,
                decision=document_decision,
                quality_score=(
                    float(document.quality_score) if document.quality_score is not None else None
                ),
                final_status=document.final_status,
                review_reason=(latest.reasons_json[0] if latest and latest.reasons_json else None),
            )
        )
    return responses


@router.get("/{task_id}/results/{decision}", response_model=list[CrawlTaskResultResponse])
async def list_task_results_by_decision(
    task_id: int,
    decision: str,
    _admin: AdminUser,
    service: CrawlServiceDependency,
) -> list[CrawlTaskResultResponse]:
    normalized = "pending_review" if decision == "pending" else decision
    if normalized not in {"accepted", "rejected", "pending_review", "failed"}:
        raise AppError("INVALID_RESULT_DECISION", "Unsupported result decision", status_code=422)
    return await list_task_results(task_id, _admin, service, normalized)


@router.post("/{task_id}/retry", response_model=CrawlTaskResponse)
async def retry_crawl_task(
    task_id: int, _admin: AdminUser, service: CrawlServiceDependency
) -> CrawlTaskResponse:
    task = await service.retry(task_id)
    await _queue_task(task.id, service, mark_queued=False)
    return CrawlTaskResponse.model_validate(task)


@router.post("/{task_id}/cancel", response_model=CrawlTaskResponse)
async def cancel_crawl_task(
    task_id: int, _admin: AdminUser, service: CrawlServiceDependency
) -> CrawlTaskResponse:
    return CrawlTaskResponse.model_validate(await service.cancel(task_id))
