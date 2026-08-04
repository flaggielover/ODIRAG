from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.retrieval import RetrievalMode


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    mode: RetrievalMode = RetrievalMode.HYBRID_RERANK
    filters: dict[str, Any] = Field(default_factory=dict)


class SearchHitResponse(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    title: str
    source_url: str
    score: float
    rank: int
    source: str
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    trace_id: str
    query: str
    mode: RetrievalMode
    filters: dict[str, Any]
    hits: list[SearchHitResponse]
    total_ms: float
    warnings: list[str]


class SearchAnalysisResponse(BaseModel):
    original_query: str
    normalized_query: str
    terms: list[str]
    inferred_filters: dict[str, Any]
    applied_filters: dict[str, Any]


class SearchConfigResponse(BaseModel):
    bm25_top_k: int
    vector_top_k: int
    rrf_k: int
    rerank_top_k: int
    final_top_k: int
    score_threshold: float


class SearchDebugResponse(SearchResponse):
    analysis: SearchAnalysisResponse
    config: SearchConfigResponse
    timings_ms: dict[str, float]
    bm25_results: list[SearchHitResponse]
    vector_results: list[SearchHitResponse]
    fusion_results: list[SearchHitResponse]
    rerank_results: list[SearchHitResponse]
