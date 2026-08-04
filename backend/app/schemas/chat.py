from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.router import QueryType


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    filters: dict[str, Any] = Field(default_factory=dict)


class CitationResponse(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    source: str
    publication_date: str | None
    url: str
    page: int | None
    quote: str


class ChatResponse(BaseModel):
    trace_id: str
    query_type: QueryType
    answer: str
    refusal: bool
    refusal_reasons: list[str]
    conflicts: list[str]
    outdated: list[str]
    citations: list[CitationResponse]
    filters: dict[str, Any]
    structured_count: int | None


class QueryTraceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trace_id: str
    user_query: str
    query_type: str
    parsed_filters_json: dict[str, Any]
    bm25_results_json: list[dict[str, Any]]
    vector_results_json: list[dict[str, Any]]
    fusion_results_json: list[dict[str, Any]]
    rerank_results_json: list[dict[str, Any]]
    final_context_json: list[dict[str, Any]]
    prompt_version: str | None
    prompt_snapshot_json: dict[str, Any]
    model_name: str | None
    answer: str | None
    citations_json: list[dict[str, Any]]
    refusal: bool
    latency_ms: int
    token_usage_json: dict[str, Any]
    cost: Decimal
    created_at: datetime
