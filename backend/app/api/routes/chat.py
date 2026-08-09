from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.config import Settings
from app.dependencies import (
    CurrentUser,
    DatabaseSession,
    get_app_settings,
    get_application_runtime,
)
from app.errors import AppError, NotFoundError
from app.rag import GroundingService
from app.repositories.chat import ChatRepository
from app.repositories.observability import ObservabilityRepository
from app.router import QueryRouter, QueryType
from app.runtime import ApplicationRuntime
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    CitationResponse,
    EvidenceSufficiencyResponse,
    QueryTraceResponse,
)
from app.schemas.observability import AnswerLineageResponse
from app.services.chat import ChatAnswer, ChatService
from app.services.observability import LineageService

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_service(
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
    runtime: Annotated[ApplicationRuntime, Depends(get_application_runtime)],
) -> ChatService:
    return ChatService(
        ChatRepository(session),
        QueryRouter(),
        runtime.retrieval_engine(),
        runtime.evidence_sufficiency_gate,
        GroundingService(
            minimum_hits=settings.grounding_minimum_hits,
            minimum_score=settings.grounding_minimum_score,
            require_official_source=settings.grounding_require_official_source,
            refuse_on_conflict=settings.grounding_refuse_on_conflict,
        ),
        orchestrator=runtime.llm_orchestrator,
        prompt=runtime.grounded_answer_prompt,
        prompt_version=runtime.grounded_answer_prompt_version,
    )


ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]


def get_lineage_service(session: DatabaseSession) -> LineageService:
    return LineageService(ObservabilityRepository(session))


LineageServiceDependency = Annotated[LineageService, Depends(get_lineage_service)]


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    _user: CurrentUser,
    service: ChatServiceDependency,
) -> ChatResponse:
    try:
        result = await service.answer(payload.query, explicit_filters=payload.filters)
    except ValueError as exc:
        raise AppError("INVALID_CHAT_REQUEST", str(exc), status_code=422) from exc
    return _response(result)


@router.get("/traces", response_model=list[QueryTraceResponse])
async def chat_traces(
    _user: CurrentUser,
    service: ChatServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    query_type: Annotated[QueryType | None, Query()] = None,
    refusal: Annotated[bool | None, Query()] = None,
) -> list[QueryTraceResponse]:
    traces = await service.list_traces(
        limit=limit,
        query_type=query_type.value if query_type is not None else None,
        refusal=refusal,
    )
    return [QueryTraceResponse.model_validate(trace) for trace in traces]


@router.get("/traces/{trace_id}", response_model=QueryTraceResponse)
async def chat_trace(
    trace_id: str,
    _user: CurrentUser,
    service: ChatServiceDependency,
) -> QueryTraceResponse:
    trace = await service.get_trace(trace_id)
    if trace is None:
        raise NotFoundError("Query trace", trace_id)
    return QueryTraceResponse.model_validate(trace)


@router.get("/traces/{trace_id}/lineage", response_model=AnswerLineageResponse)
async def chat_trace_lineage(
    trace_id: str,
    _user: CurrentUser,
    service: LineageServiceDependency,
) -> AnswerLineageResponse:
    return await service.answer_lineage(trace_id)


def _response(result: ChatAnswer) -> ChatResponse:
    return ChatResponse(
        trace_id=result.trace_id,
        query_type=result.query_type,
        answer=result.answer,
        refusal=result.refusal,
        refusal_reasons=list(result.refusal_reasons),
        conflicts=list(result.conflicts),
        outdated=list(result.outdated),
        citations=[
            CitationResponse(
                document_id=citation.document_id,
                chunk_id=citation.chunk_id,
                title=citation.title,
                source=citation.source,
                publication_date=citation.publication_date,
                url=citation.url,
                page=citation.page,
                quote=citation.quote,
            )
            for citation in result.citations
        ],
        filters=result.filters,
        structured_count=result.structured_count,
        evidence_sufficiency=(
            EvidenceSufficiencyResponse(**result.evidence_sufficiency.as_dict())
            if result.evidence_sufficiency is not None
            else None
        ),
    )
