from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.config import Settings
from app.dependencies import (
    AdminUser,
    CurrentUser,
    DatabaseSession,
    get_app_settings,
    get_application_runtime,
)
from app.errors import AppError, NotFoundError
from app.experiments import ExperimentExecutionError
from app.repositories.evaluation import ExperimentRepository
from app.runtime import ApplicationRuntime
from app.schemas.experiment import (
    ExperimentCreateRequest,
    ExperimentResponse,
    ExperimentRunRequest,
)
from app.services.experiments import ExperimentApplicationService

router = APIRouter(prefix="/experiments", tags=["experiments"])


def get_experiment_service(
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
    runtime: Annotated[ApplicationRuntime, Depends(get_application_runtime)],
) -> ExperimentApplicationService:
    return ExperimentApplicationService(
        ExperimentRepository(session),
        settings=settings,
        runtime=runtime,
    )


ExperimentServiceDependency = Annotated[
    ExperimentApplicationService, Depends(get_experiment_service)
]


@router.post("", response_model=ExperimentResponse)
async def create_experiment(
    payload: ExperimentCreateRequest,
    _admin: AdminUser,
    service: ExperimentServiceDependency,
) -> ExperimentResponse:
    experiment = await service.create(payload)
    return ExperimentResponse.model_validate(experiment)


@router.get("", response_model=list[ExperimentResponse])
async def list_experiments(
    _user: CurrentUser,
    service: ExperimentServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ExperimentResponse]:
    experiments = await service.list(limit=limit)
    return [ExperimentResponse.model_validate(experiment) for experiment in experiments]


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: int,
    _user: CurrentUser,
    service: ExperimentServiceDependency,
) -> ExperimentResponse:
    experiment = await service.get(experiment_id)
    if experiment is None:
        raise NotFoundError("Experiment", experiment_id)
    return ExperimentResponse.model_validate(experiment)


@router.post("/{experiment_id}/run", response_model=ExperimentResponse)
async def run_experiment(
    experiment_id: int,
    payload: ExperimentRunRequest,
    _admin: AdminUser,
    service: ExperimentServiceDependency,
) -> ExperimentResponse:
    experiment = await service.get(experiment_id)
    if experiment is None:
        raise NotFoundError("Experiment", experiment_id)
    try:
        completed = await service.run(experiment, payload)
    except (ValueError, ExperimentExecutionError) as exc:
        raise AppError("EXPERIMENT_EXECUTION_FAILED", str(exc), status_code=409) from exc
    return ExperimentResponse.model_validate(completed)


@router.get("/{experiment_id}/compare", response_model=dict[str, Any])
async def compare_experiment(
    experiment_id: int,
    _user: CurrentUser,
    service: ExperimentServiceDependency,
) -> dict[str, Any]:
    experiment = await service.get(experiment_id)
    if experiment is None:
        raise NotFoundError("Experiment", experiment_id)
    try:
        return await service.compare(experiment)
    except ExperimentExecutionError as exc:
        raise AppError("EXPERIMENT_REPORT_UNAVAILABLE", str(exc), status_code=409) from exc
