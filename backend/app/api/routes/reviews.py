from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import Settings
from app.dependencies import AdminUser, DatabaseSession, get_app_settings
from app.filters import RuleFilter
from app.llm import CozeAdapter, DirectLLMAdapter, LLMOrchestrator
from app.repositories.reviews import ReviewRepository
from app.schemas.review import (
    ManualReviewRequest,
    PendingReviewDocument,
    ReviewActionResponse,
    ReviewPipelineResponse,
)
from app.services.filter_config import load_filter_config
from app.services.review import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"])


def get_review_service(
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ReviewService:
    orchestrator: LLMOrchestrator
    if settings.llm_provider == "coze":
        orchestrator = CozeAdapter(
            base_url=settings.coze_base_url,
            api_token=(
                settings.coze_api_token.get_secret_value() if settings.coze_api_token else None
            ),
            bot_id=settings.coze_bot_id,
        )
    else:
        orchestrator = DirectLLMAdapter(
            base_url=settings.direct_llm_base_url,
            api_key=(
                settings.direct_llm_api_key.get_secret_value()
                if settings.direct_llm_api_key
                else None
            ),
            model_name=settings.direct_llm_model,
        )
    return ReviewService(
        ReviewRepository(session),
        RuleFilter(load_filter_config(settings.review_filter_config_path)),
        orchestrator,
        prompt_name=settings.review_prompt_name,
        prompt_version=settings.review_prompt_version,
        prompt_content=settings.review_prompt_path.read_text(encoding="utf-8"),
    )


ReviewServiceDependency = Annotated[ReviewService, Depends(get_review_service)]


@router.get("/pending", response_model=list[PendingReviewDocument])
async def pending_reviews(
    _admin: AdminUser, service: ReviewServiceDependency
) -> list[PendingReviewDocument]:
    return [PendingReviewDocument.model_validate(document) for document in await service.pending()]


@router.post("/{document_id}/run", response_model=ReviewPipelineResponse)
async def run_review(
    document_id: int, _admin: AdminUser, service: ReviewServiceDependency
) -> ReviewPipelineResponse:
    result = await service.run(document_id)
    return ReviewPipelineResponse(
        document_id=result.document_id,
        rule_decision=result.rule_decision,
        rule_score=result.rule_score,
        llm_decision=result.llm_decision,
        final_status=result.final_status,
        extracted_fields=result.extracted_fields,
    )


@router.post("/{document_id}/approve", response_model=ReviewActionResponse)
async def approve_document(
    document_id: int, admin: AdminUser, service: ReviewServiceDependency
) -> ReviewActionResponse:
    document = await service.manual_decision(
        document_id, decision="approve", reviewer=admin.username
    )
    return ReviewActionResponse(
        document_id=document.id, decision="approve", final_status=document.final_status
    )


@router.post("/{document_id}/reject", response_model=ReviewActionResponse)
async def reject_document(
    document_id: int, admin: AdminUser, service: ReviewServiceDependency
) -> ReviewActionResponse:
    document = await service.manual_decision(
        document_id, decision="reject", reviewer=admin.username
    )
    return ReviewActionResponse(
        document_id=document.id, decision="reject", final_status=document.final_status
    )


@router.post("/{document_id}/manual-review", response_model=ReviewActionResponse)
async def manual_review(
    document_id: int,
    payload: ManualReviewRequest,
    admin: AdminUser,
    service: ReviewServiceDependency,
) -> ReviewActionResponse:
    document = await service.manual_decision(
        document_id,
        decision=payload.decision,
        reviewer=admin.username,
        summary=payload.summary,
        reasons=payload.reasons,
    )
    return ReviewActionResponse(
        document_id=document.id,
        decision=payload.decision,
        final_status=document.final_status,
    )
