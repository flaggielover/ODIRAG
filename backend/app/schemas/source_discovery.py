from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ExecutionMode = Literal["queued", "inline"]


class SourceDiscoveryRunCreate(BaseModel):
    topic: str = Field(min_length=1, max_length=255)
    region: str | None = Field(default=None, max_length=128)
    organization_level: str | None = Field(default=None, max_length=64)
    query_text: str | None = Field(default=None, max_length=1_000)
    required_source_count: int = Field(default=1, ge=1, le=100)
    required_document_count: int = Field(default=3, ge=0, le=10_000)
    max_candidates: int | None = Field(default=None, ge=1, le=100)
    execution_mode: ExecutionMode = "queued"


class SourceDiscoveryRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    region: str | None
    organization_level: str | None
    query_text: str
    required_source_count: int
    required_document_count: int
    existing_source_count: int
    existing_document_count: int
    gap_detected: bool
    gap_evidence_json: dict[str, Any]
    status: str
    discovery_provider: str
    max_candidates: int
    candidate_count: int
    approved_count: int
    activated_count: int
    attempt_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class SourceCandidateColumnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    column_key: str
    column_name: str
    column_url: str
    parser_type: str
    selectors_json: dict[str, Any]
    pagination_json: dict[str, Any]
    discovery_evidence_json: dict[str, Any]
    status: str
    trial_discovered_count: int
    trial_fetched_count: int
    trial_success_count: int
    trial_failed_count: int
    trial_average_chars: int
    quality_score: float | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class SourceCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    canonical_homepage_url: str
    domain: str
    name: str
    snippet: str | None
    search_rank: int | None
    discovery_provider: str
    discovery_query: str
    official_status: str
    official_score: float | None
    official_evidence_json: dict[str, Any]
    validation_status_code: int | None
    validation_final_url: str | None
    status: str
    quality_score: float | None
    quality_breakdown_json: dict[str, Any]
    trial_column_count: int
    trial_document_count: int
    trial_success_count: int
    trial_failed_count: int
    trial_average_chars: int
    rejection_reason: str | None
    approved_by: str | None
    approved_at: datetime | None
    source_id: int | None
    created_at: datetime
    updated_at: datetime
    columns: list[SourceCandidateColumnResponse] = Field(default_factory=list)


class SourceCandidateDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=2_000)


class SourceDiscoveryEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    candidate_id: int | None
    stage: str
    from_status: str | None
    to_status: str
    message: str
    details_json: dict[str, Any]
    created_at: datetime


class SourceDiscoveryMetricsResponse(BaseModel):
    run_status_counts: dict[str, int]
    candidate_status_counts: dict[str, int]
    column_status_counts: dict[str, int]
    pending_approval_count: int
    activated_source_count: int
    average_quality_score: float
    last_run_at: datetime | None
