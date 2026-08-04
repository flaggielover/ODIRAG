from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import AdminUser, CurrentUser, DatabaseSession
from app.repositories.feedback import FeedbackRepository
from app.schemas.feedback import FeedbackCreate, FeedbackResponse, FeedbackType
from app.services.feedback import FeedbackService

router = APIRouter(prefix="/feedback", tags=["feedback"])


def get_feedback_service(session: DatabaseSession) -> FeedbackService:
    return FeedbackService(FeedbackRepository(session))


FeedbackServiceDependency = Annotated[FeedbackService, Depends(get_feedback_service)]


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    payload: FeedbackCreate,
    _user: CurrentUser,
    service: FeedbackServiceDependency,
) -> FeedbackResponse:
    return FeedbackResponse.model_validate(await service.create(payload))


@router.get("", response_model=list[FeedbackResponse])
async def list_feedback(
    _admin: AdminUser,
    service: FeedbackServiceDependency,
    resolved: Annotated[bool | None, Query()] = None,
    feedback_type: Annotated[FeedbackType | None, Query()] = None,
    converted_to_evaluation: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FeedbackResponse]:
    items = await service.list(
        resolved=resolved,
        feedback_type=feedback_type,
        converted_to_evaluation=converted_to_evaluation,
        limit=limit,
    )
    return [FeedbackResponse.model_validate(item) for item in items]


@router.post("/{feedback_id}/convert-to-evaluation", response_model=FeedbackResponse)
async def convert_feedback_to_evaluation(
    feedback_id: int,
    _admin: AdminUser,
    service: FeedbackServiceDependency,
) -> FeedbackResponse:
    return FeedbackResponse.model_validate(await service.convert_to_evaluation(feedback_id))
