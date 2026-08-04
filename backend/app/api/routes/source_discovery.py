from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.config import Settings
from app.dependencies import AdminUser, DatabaseSession, get_app_settings
from app.errors import AppError
from app.repositories.source_discovery import SourceDiscoveryRepository
from app.schemas.source_discovery import (
    SourceCandidateColumnResponse,
    SourceCandidateDecision,
    SourceCandidateResponse,
    SourceDiscoveryEventResponse,
    SourceDiscoveryMetricsResponse,
    SourceDiscoveryRunCreate,
    SourceDiscoveryRunResponse,
)
from app.services.source_discovery import SourceDiscoveryService
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/source-discovery", tags=["source-discovery"])


def get_source_discovery_service(
    request: Request,
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SourceDiscoveryService:
    # Tests and controlled deployments may inject a contract-compatible provider.
    provider = getattr(request.app.state, "source_discovery_provider", None)
    fetcher = getattr(request.app.state, "source_discovery_fetcher", None)
    return SourceDiscoveryService(
        SourceDiscoveryRepository(session), settings, provider=provider, fetcher=fetcher
    )


SourceDiscoveryServiceDependency = Annotated[
    SourceDiscoveryService, Depends(get_source_discovery_service)
]


async def _queue_run(run_id: int, service: SourceDiscoveryService) -> None:
    try:
        celery_app.send_task("odirag.source_discovery.run", args=[run_id])
    except Exception as exc:
        await service.mark_queue_failure(run_id, exc.__class__.__name__)
        raise AppError(
            "SOURCE_DISCOVERY_QUEUE_UNAVAILABLE",
            "Discovery run was persisted but could not be queued",
            status_code=503,
            details={"run_id": run_id, "error_type": exc.__class__.__name__},
        ) from exc


@router.get("/metrics", response_model=SourceDiscoveryMetricsResponse)
async def source_discovery_metrics(
    _admin: AdminUser, service: SourceDiscoveryServiceDependency
) -> SourceDiscoveryMetricsResponse:
    return SourceDiscoveryMetricsResponse.model_validate(await service.metrics())


@router.post(
    "/runs", response_model=SourceDiscoveryRunResponse, status_code=status.HTTP_201_CREATED
)
async def create_source_discovery_run(
    payload: SourceDiscoveryRunCreate,
    admin: AdminUser,
    service: SourceDiscoveryServiceDependency,
) -> SourceDiscoveryRunResponse:
    run = await service.create(payload, created_by=admin.username)
    if run.status == "pending":
        if payload.execution_mode == "inline":
            run = await service.execute(run.id)
        else:
            await _queue_run(run.id, service)
    return SourceDiscoveryRunResponse.model_validate(run)


@router.get("/runs", response_model=list[SourceDiscoveryRunResponse])
async def list_source_discovery_runs(
    _admin: AdminUser,
    service: SourceDiscoveryServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[SourceDiscoveryRunResponse]:
    return [
        SourceDiscoveryRunResponse.model_validate(run)
        for run in await service.list_runs(limit=limit)
    ]


@router.get("/runs/{run_id}", response_model=SourceDiscoveryRunResponse)
async def get_source_discovery_run(
    run_id: int, _admin: AdminUser, service: SourceDiscoveryServiceDependency
) -> SourceDiscoveryRunResponse:
    return SourceDiscoveryRunResponse.model_validate(await service.get_run(run_id))


@router.get("/runs/{run_id}/candidates", response_model=list[SourceCandidateResponse])
async def list_run_candidates(
    run_id: int, _admin: AdminUser, service: SourceDiscoveryServiceDependency
) -> list[SourceCandidateResponse]:
    candidates = await service.list_candidates(run_id)
    return [await _candidate_response(service, candidate.id) for candidate in candidates]


@router.get("/runs/{run_id}/events", response_model=list[SourceDiscoveryEventResponse])
async def list_run_events(
    run_id: int,
    _admin: AdminUser,
    service: SourceDiscoveryServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> list[SourceDiscoveryEventResponse]:
    await service.get_run(run_id)
    events = await service.repository.list_events(run_id=run_id, limit=limit)
    return [SourceDiscoveryEventResponse.model_validate(event) for event in events]


@router.post("/runs/{run_id}/retry", response_model=SourceDiscoveryRunResponse)
async def retry_source_discovery_run(
    run_id: int, _admin: AdminUser, service: SourceDiscoveryServiceDependency
) -> SourceDiscoveryRunResponse:
    run = await service.retry(run_id)
    await _queue_run(run.id, service)
    return SourceDiscoveryRunResponse.model_validate(run)


@router.get("/candidates/{candidate_id}", response_model=SourceCandidateResponse)
async def get_source_candidate(
    candidate_id: int, _admin: AdminUser, service: SourceDiscoveryServiceDependency
) -> SourceCandidateResponse:
    return await _candidate_response(service, candidate_id)


@router.get("/candidates/{candidate_id}/events", response_model=list[SourceDiscoveryEventResponse])
async def list_candidate_events(
    candidate_id: int,
    _admin: AdminUser,
    service: SourceDiscoveryServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> list[SourceDiscoveryEventResponse]:
    candidate = await service.get_candidate(candidate_id)
    events = await service.repository.list_events(
        run_id=candidate.run_id, candidate_id=candidate_id, limit=limit
    )
    return [SourceDiscoveryEventResponse.model_validate(event) for event in events]


@router.post("/candidates/{candidate_id}/approve", response_model=SourceCandidateResponse)
async def approve_source_candidate(
    candidate_id: int,
    admin: AdminUser,
    service: SourceDiscoveryServiceDependency,
) -> SourceCandidateResponse:
    candidate = await service.approve(candidate_id, admin.username)
    return await _candidate_response(service, candidate.id)


@router.post("/candidates/{candidate_id}/reject", response_model=SourceCandidateResponse)
async def reject_source_candidate(
    candidate_id: int,
    payload: SourceCandidateDecision,
    admin: AdminUser,
    service: SourceDiscoveryServiceDependency,
) -> SourceCandidateResponse:
    candidate = await service.reject(candidate_id, admin.username, payload.reason)
    return await _candidate_response(service, candidate.id)


@router.post("/candidates/{candidate_id}/activate", response_model=SourceCandidateResponse)
async def activate_source_candidate(
    candidate_id: int,
    _admin: AdminUser,
    service: SourceDiscoveryServiceDependency,
) -> SourceCandidateResponse:
    candidate = await service.activate(candidate_id)
    return await _candidate_response(service, candidate.id)


async def _candidate_response(
    service: SourceDiscoveryService, candidate_id: int
) -> SourceCandidateResponse:
    candidate, columns, _events = await service.candidate_detail(candidate_id)
    payload = SourceCandidateResponse.model_validate(candidate)
    payload.columns = [SourceCandidateColumnResponse.model_validate(column) for column in columns]
    return payload
