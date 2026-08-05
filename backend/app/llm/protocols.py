from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMResultBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token_usage: dict[str, int] = Field(default_factory=dict, exclude=True)
    cost: Decimal | None = Field(default=None, exclude=True)


class ReviewResult(LLMResultBase):
    decision: Literal["approve", "reject", "manual_review"]
    quality_score: float = Field(ge=0, le=1)
    document_type: str | None = None
    topics: list[str] = Field(default_factory=list)
    summary: str = ""
    reasons: list[str] = Field(default_factory=list)
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    raw_response: str | None = Field(default=None, exclude=True)


class QueryPlan(LLMResultBase):
    query_type: Literal["sql", "rag", "sql+rag"]
    rewritten_query: str
    filters: dict[str, Any] = Field(default_factory=dict)


class AnswerResult(LLMResultBase):
    answer: str
    cited_chunk_ids: list[str] = Field(default_factory=list)
    refusal: bool = False
    refusal_reason: str | None = None


class EvidenceCheck(LLMResultBase):
    sufficient: bool
    covered_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class LLMOrchestrator(Protocol):
    model_name: str

    async def review_document(self, *, title: str, content: str, prompt: str) -> ReviewResult: ...

    async def analyze_query(self, *, query: str, prompt: str) -> QueryPlan: ...

    async def generate_answer(
        self, *, query: str, context: list[dict[str, Any]], prompt: str
    ) -> AnswerResult: ...

    async def check_evidence(
        self, *, query: str, context: list[dict[str, Any]], prompt: str
    ) -> EvidenceCheck: ...
