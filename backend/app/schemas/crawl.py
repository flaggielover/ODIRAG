from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CrawlTaskCreate(BaseModel):
    source_column_id: int = Field(gt=0)
    task_type: Literal["full", "incremental"] = "incremental"
    trigger_type: Literal["manual", "schedule", "retry"] = "manual"
    execution_mode: Literal["queued", "inline"] = "queued"
    provider_contract: Literal["legacy_single_article", "batch_crawl"] | None = None
    provider: Literal["coze", "local"] | None = None
    contract_mode: Literal["legacy_single_article", "batch_crawl"] | None = None
    max_articles: int = Field(default=5, ge=1, le=100)
    max_pages: int = Field(default=1, ge=1, le=100)


class CrawlTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_column_id: int
    task_type: str
    trigger_type: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    discovered_count: int
    fetched_count: int
    success_count: int
    url_duplicate_count: int
    content_duplicate_count: int
    semantic_duplicate_count: int
    failed_count: int
    retry_count: int
    error_message: str | None
    crawl_provider: str
    provider_contract: str | None
    provider_task_id: str | None
    provider_status: str | None
    provider_error_code: str | None
    max_articles: int
    max_pages: int
    created_at: datetime
    provider: str
    contract_mode: str
    current_stage: str
    provider_error_message: str | None
    coze_execution_id: str | None
    accepted_count: int
    rejected_count: int
    pending_review_count: int
    next_retry_at: datetime | None
    completed_at: datetime | None


class CrawlTaskFailureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    crawl_task_id: int
    url: str
    stage: str
    error_code: str
    error_message: str
    retryable: bool
    status: str
    retry_count: int
    last_attempt_at: datetime | None
    next_retry_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CrawlTaskResultResponse(BaseModel):
    id: int
    document_id: str
    title: str
    source_url: str
    decision: str
    quality_score: float | None
    final_status: str
    review_reason: str | None = None


class CrawlTaskAcceptanceSummaryResponse(BaseModel):
    crawl_task_id: int
    database_document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    qdrant_collection_exists: bool
    qdrant_point_count: int = Field(ge=0)


class CozeInvocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    crawl_task_id: int
    contract: str
    endpoint_url: str
    deployment_identifier: str
    source_id: int
    status: str
    request_json: Any
    raw_response_json: Any | None
    normalized_response_json: Any | None
    http_status_code: int | None
    attempt_count: int
    retry_count: int
    duration_ms: int | None
    token_usage_json: dict[str, Any]
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
