from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
    confidence: float = Field(ge=0, le=1)
    evidence_quote: str = Field(min_length=1)


class ManualReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    summary: str | None = None
    reasons: list[str] = Field(default_factory=list)


class PendingReviewDocument(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: str
    title: str
    source_url: str
    rule_filter_status: str
    llm_review_status: str
    manual_review_status: str
    final_status: str
    created_at: datetime


class ReviewActionResponse(BaseModel):
    document_id: int
    decision: str
    final_status: str


class ReviewPipelineResponse(BaseModel):
    document_id: int
    rule_decision: str
    rule_score: float
    llm_decision: str | None
    final_status: str
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
