from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.config import Settings
from app.dependencies import AdminUser, DatabaseSession, get_app_settings
from app.metrics import MetricsRegistry
from app.repositories.observability import ObservabilityRepository
from app.schemas.observability import AlertResponse, AlertSeverity, AlertStatus
from app.schemas.system import (
    CozeCrawlConfigResponse,
    CozeStatusResponse,
    HealthResponse,
    MetricsResponse,
)
from app.services.health import HealthService
from app.services.observability import MonitoringService

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/coze/status", response_model=CozeStatusResponse)
async def coze_status(
    _admin: AdminUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> CozeStatusResponse:
    return CozeStatusResponse(
        enabled=settings.coze_enabled,
        token_configured=settings.coze_api_token is not None,
        legacy_workflow_configured=bool(settings.coze_legacy_api_url),
        batch_workflow_configured=bool(settings.coze_batch_api_url),
        default_contract=settings.coze_default_contract,
    )


@router.get("/coze-crawl-config", response_model=CozeCrawlConfigResponse)
async def coze_crawl_config(
    _admin: AdminUser,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> CozeCrawlConfigResponse:
    return CozeCrawlConfigResponse(
        enabled=settings.coze_enabled,
        token_configured=settings.coze_api_token is not None,
        legacy_workflow_configured=bool(settings.coze_legacy_api_url),
        batch_workflow_configured=bool(settings.coze_batch_api_url),
        default_contract=settings.coze_default_contract,
    )


@router.get("/health", response_model=HealthResponse, summary="Check service dependencies")
async def health(
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> HealthResponse:
    return await HealthService(session, settings).check()


@router.get("/metrics", response_model=MetricsResponse, summary="Return process metrics")
async def metrics(
    request: Request,
    _admin: AdminUser,
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> MetricsResponse:
    registry: MetricsRegistry = request.app.state.metrics
    process = await registry.snapshot()
    operational = await MonitoringService(ObservabilityRepository(session), settings).metrics()
    dependency_health = await HealthService(session, settings).check()
    return MetricsResponse.model_validate(
        {
            **process,
            "crawler": operational.crawler,
            "knowledge": operational.knowledge,
            "rag": operational.rag,
            "dependencies": dependency_health.dependencies,
        }
    )


@router.get("/alerts", response_model=list[AlertResponse])
async def alerts(
    _admin: AdminUser,
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
    status: Annotated[AlertStatus | None, Query()] = None,
    severity: Annotated[AlertSeverity | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    refresh: bool = True,
) -> list[AlertResponse]:
    repository = ObservabilityRepository(session)
    service = MonitoringService(repository, settings)
    if refresh:
        operational = await service.metrics()
        health_response = await HealthService(session, settings).check()
        await service.refresh_alerts(operational, health_response)
    stored = await repository.list_alerts(
        status=status,
        severity=severity,
        limit=limit,
    )
    return [AlertResponse.model_validate(alert) for alert in stored]


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    _admin: AdminUser,
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AlertResponse:
    alert = await MonitoringService(ObservabilityRepository(session), settings).acknowledge(
        alert_id
    )
    return AlertResponse.model_validate(alert)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: int,
    _admin: AdminUser,
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AlertResponse:
    alert = await MonitoringService(ObservabilityRepository(session), settings).resolve(alert_id)
    return AlertResponse.model_validate(alert)
