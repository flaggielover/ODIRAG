from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.routes.chat import get_chat_service
from app.config import Settings
from app.dependencies import (
    AdminUser,
    CurrentUser,
    DatabaseSession,
    get_app_settings,
    get_application_runtime,
)
from app.errors import AppError, NotFoundError
from app.repositories.evaluation import EvaluationRepository
from app.runtime import ApplicationRuntime, resolve_runtime_path
from app.schemas.evaluation import (
    EvaluationMatrixRequest,
    EvaluationMatrixResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
)
from app.services.evaluation import EvaluationApplicationService

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


def get_evaluation_service(
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
    runtime: Annotated[ApplicationRuntime, Depends(get_application_runtime)],
) -> EvaluationApplicationService:
    return EvaluationApplicationService(
        EvaluationRepository(session),
        get_chat_service(session, settings, runtime),
        artifact_root=resolve_runtime_path(settings.evaluation_artifact_dir),
        embedding_model=runtime.embedding_provider.model_name,
        rerank_model=getattr(runtime.rerank_provider, "model_name", None),
        default_retrieval_version="hybrid-rrf-rerank-v1",
        default_prompt_version=runtime.grounded_answer_prompt_version,
    )


EvaluationServiceDependency = Annotated[
    EvaluationApplicationService, Depends(get_evaluation_service)
]


@router.post("/run", response_model=EvaluationRunResponse)
async def run_evaluation(
    payload: EvaluationRunRequest,
    _admin: AdminUser,
    service: EvaluationServiceDependency,
) -> EvaluationRunResponse:
    try:
        run = await service.run(payload)
    except ValueError as exc:
        raise AppError("INVALID_EVALUATION_REQUEST", str(exc), status_code=422) from exc
    return EvaluationRunResponse.model_validate(run)


@router.post("/matrix", response_model=EvaluationMatrixResponse)
async def run_evaluation_matrix(
    payload: EvaluationMatrixRequest,
    _admin: AdminUser,
    service: EvaluationServiceDependency,
) -> EvaluationMatrixResponse:
    try:
        result = await service.run_matrix(payload)
    except ValueError as exc:
        raise AppError("INVALID_EVALUATION_REQUEST", str(exc), status_code=422) from exc
    return EvaluationMatrixResponse.model_validate(result)


@router.get("", response_model=list[EvaluationRunResponse])
async def list_evaluations(
    _user: CurrentUser,
    service: EvaluationServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[EvaluationRunResponse]:
    runs = await service.list_runs(limit=limit)
    return [EvaluationRunResponse.model_validate(run) for run in runs]


@router.get("/{run_id}", response_model=EvaluationRunResponse)
async def get_evaluation(
    run_id: int,
    _user: CurrentUser,
    service: EvaluationServiceDependency,
) -> EvaluationRunResponse:
    run = await service.get_run(run_id)
    if run is None:
        raise NotFoundError("Evaluation run", run_id)
    return EvaluationRunResponse.model_validate(run)


@router.get("/{run_id}/report", response_model=dict[str, Any])
async def get_evaluation_report(
    run_id: int,
    _user: CurrentUser,
    service: EvaluationServiceDependency,
) -> dict[str, Any]:
    run = await service.get_run(run_id)
    if run is None:
        raise NotFoundError("Evaluation run", run_id)
    try:
        return await service.report(run)
    except ValueError as exc:
        raise AppError("EVALUATION_REPORT_UNAVAILABLE", str(exc), status_code=409) from exc
