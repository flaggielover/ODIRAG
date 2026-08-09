from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.retrieval import RetrievalMode


class EvaluationQuestionInput(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=4000)
    query_type: Literal["sql", "rag", "sql+rag"]
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_answer_points: list[str] = Field(default_factory=list)
    expected_filters: dict[str, Any] = Field(default_factory=dict)
    should_refuse: bool = False
    difficulty: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=128)
    created_by: str | None = Field(default=None, max_length=255)
    verified: bool = True


class EvaluationRunRequest(BaseModel):
    run_name: str = Field(min_length=1, max_length=255)
    question_ids: list[str] = Field(default_factory=list)
    questions: list[EvaluationQuestionInput] = Field(default_factory=list)
    category: str | None = Field(default=None, max_length=128)
    retrieval_mode: RetrievalMode = RetrievalMode.HYBRID_RERANK
    retrieval_version: str | None = Field(default=None, max_length=48)
    prompt_version: str | None = Field(default=None, max_length=64)
    top_k: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def require_verified_inline_questions(self) -> EvaluationRunRequest:
        if any(not question.verified for question in self.questions):
            raise ValueError("evaluation runs only accept verified questions")
        return self


class EvaluationMatrixRequest(BaseModel):
    matrix_name: str = Field(min_length=1, max_length=220)
    question_ids: list[str] = Field(default_factory=list)
    questions: list[EvaluationQuestionInput] = Field(default_factory=list)
    category: str | None = Field(default=None, max_length=128)
    retrieval_version: str | None = Field(default=None, max_length=48)
    prompt_version: str | None = Field(default=None, max_length=64)
    top_k: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def require_verified_inline_questions(self) -> EvaluationMatrixRequest:
        if any(not question.verified for question in self.questions):
            raise ValueError("evaluation matrices only accept verified questions")
        return self


class EvaluationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_name: str
    experiment_id: int | None
    retrieval_version: str | None
    prompt_version: str | None
    embedding_model: str | None
    rerank_model: str | None
    top_k: int
    started_at: datetime | None
    finished_at: datetime | None
    question_count: int
    recall_at_1: Decimal | None
    recall_at_5: Decimal | None
    recall_at_10: Decimal | None
    mrr: Decimal | None
    ndcg: Decimal | None
    citation_accuracy: Decimal | None
    refusal_accuracy: Decimal | None
    hallucination_rate: Decimal | None
    average_latency: Decimal | None
    p95_latency: Decimal | None
    average_cost: Decimal | None
    result_path: str | None
    created_at: datetime


class EvaluationMatrixRunResponse(BaseModel):
    retrieval_mode: RetrievalMode
    run_id: int
    run_name: str
    top_k: int
    question_ids: list[str]
    aggregate: dict[str, float | int]
    result_path: str


class EvaluationMatrixResponse(BaseModel):
    matrix_name: str
    top_k: int
    question_ids: list[str]
    runs: list[EvaluationMatrixRunResponse]
    measurement_notes: list[str]


class EvaluationReportResponse(BaseModel):
    run_id: int
    run_name: str
    aggregate: dict[str, float | int]
    cases: list[dict[str, Any]]
    artifacts: dict[str, str]
    measurement_notes: list[str] = Field(default_factory=list)
