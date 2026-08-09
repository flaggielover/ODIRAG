from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AdminUser, CurrentUser, get_application_runtime
from app.errors import AppError
from app.retrieval import RetrievalEngine, RetrievalHit, RetrievalTrace
from app.runtime import ApplicationRuntime
from app.schemas.search import (
    SearchAnalysisResponse,
    SearchConfigResponse,
    SearchDebugResponse,
    SearchHitResponse,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(prefix="/search", tags=["search"])


def get_retrieval_engine(
    runtime: Annotated[ApplicationRuntime, Depends(get_application_runtime)],
) -> RetrievalEngine:
    return runtime.retrieval_engine()


RetrievalEngineDependency = Annotated[RetrievalEngine, Depends(get_retrieval_engine)]


@router.post("", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    _user: CurrentUser,
    engine: RetrievalEngineDependency,
) -> SearchResponse:
    return _response(await _search(engine, payload))


@router.post("/debug", response_model=SearchDebugResponse)
async def search_debug(
    payload: SearchRequest,
    _admin: AdminUser,
    engine: RetrievalEngineDependency,
) -> SearchDebugResponse:
    trace = await _search(engine, payload)
    base = _response(trace)
    return SearchDebugResponse(
        **base.model_dump(),
        analysis=SearchAnalysisResponse(
            original_query=trace.analysis.original_query,
            normalized_query=trace.analysis.normalized_query,
            terms=list(trace.analysis.terms),
            inferred_filters=trace.analysis.inferred_filters,
            applied_filters=trace.analysis.applied_filters,
        ),
        config=SearchConfigResponse(
            bm25_top_k=trace.config.bm25_top_k,
            vector_top_k=trace.config.vector_top_k,
            rrf_k=trace.config.rrf_k,
            rerank_top_k=trace.config.rerank_top_k,
            final_top_k=trace.config.final_top_k,
            score_threshold=trace.config.score_threshold,
        ),
        timings_ms=trace.timings_ms,
        bm25_results=_hits(trace.bm25_results),
        vector_results=_hits(trace.vector_results),
        fusion_results=_hits(trace.fusion_results),
        rerank_results=_hits(trace.rerank_results),
    )


def _response(trace: RetrievalTrace) -> SearchResponse:
    return SearchResponse(
        trace_id=trace.trace_id,
        query=trace.query,
        mode=trace.mode,
        filters=trace.filters,
        hits=_hits(trace.final_results),
        total_ms=trace.timings_ms["total"],
        warnings=list(trace.warnings),
        rerank_applied=bool(trace.rerank_metadata.get("applied", False)),
        rerank_metadata=trace.rerank_metadata,
    )


async def _search(engine: RetrievalEngine, payload: SearchRequest) -> RetrievalTrace:
    try:
        return await engine.search(payload.query, mode=payload.mode, filters=payload.filters)
    except ValueError as exc:
        raise AppError(
            "INVALID_SEARCH_REQUEST",
            str(exc),
            status_code=422,
        ) from exc


def _hits(hits: tuple[RetrievalHit, ...]) -> list[SearchHitResponse]:
    return [
        SearchHitResponse(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            content=hit.content,
            title=hit.title,
            source_url=hit.source_url,
            score=hit.score,
            rank=hit.rank,
            source=hit.source,
            metadata=hit.metadata,
        )
        for hit in hits
    ]
