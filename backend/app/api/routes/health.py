from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response

from app.config import Settings
from app.dependencies import get_app_settings, get_database_manager
from app.schemas.system import DependencyHealth, HealthResponse
from app.services.health import HealthService

router = APIRouter(prefix="/health", tags=["health"])

_REQUIRED_DEPENDENCIES = ("database", "redis", "qdrant")


@router.get("/live", response_model=dict[str, str], summary="Check process liveness")
async def live() -> dict[str, str]:
    """Return a dependency-free liveness response.

    This endpoint is intentionally constant-time and must remain usable while
    backing services are unavailable.  Container and load-balancer probes can
    therefore distinguish a running process from a ready application.
    """

    return {"status": "ok"}


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
    summary="Check production dependency readiness",
)
async def ready(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> HealthResponse:
    """Return dependency health and fail closed unless every dependency is live.

    The existing ``/api/system/health`` endpoint intentionally preserves its
    historical degraded-but-200 contract.  This root probe is stricter for
    orchestrators: a disabled or unavailable dependency is not ready.
    """

    try:
        database = get_database_manager(request)
        async with database.session_factory() as session:
            health = await HealthService(session, settings).check()
    except Exception as exc:
        # Do not return driver/URL/credential details from a probe.  Keep only
        # the exception type in structured logs for operators.
        structlog.get_logger(__name__).warning(
            "readiness_check_failed",
            error_type=exc.__class__.__name__,
        )
        health = _unavailable_health(settings)

    if not _is_strictly_ready(health):
        health = health.model_copy(update={"status": "degraded"})
        response.status_code = 503
    return health


def _is_strictly_ready(health: HealthResponse) -> bool:
    """Return true only when all required dependencies report ``healthy``."""

    return all(
        health.dependencies.get(name) is not None and health.dependencies[name].status == "healthy"
        for name in _REQUIRED_DEPENDENCIES
    )


def _unavailable_health(settings: Settings) -> HealthResponse:
    """Build a safe response when the health service itself cannot run."""

    return HealthResponse(
        status="degraded",
        service=settings.app_name,
        environment=settings.environment,
        checked_at=datetime.now(UTC),
        dependencies={
            name: DependencyHealth(status="unavailable", detail="check failed")
            for name in _REQUIRED_DEPENDENCIES
        },
    )
