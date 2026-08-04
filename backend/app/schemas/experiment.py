from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.evaluation import EvaluationQuestionInput


class ExperimentCreateRequest(BaseModel):
    experiment_name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    )
    experiment_type: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    )
    baseline_config: dict[str, Any] = Field(min_length=1)
    candidate_config: dict[str, Any] = Field(min_length=1)


class ExperimentRunRequest(BaseModel):
    question_ids: list[str] = Field(default_factory=list)
    questions: list[EvaluationQuestionInput] = Field(default_factory=list)
    category: str | None = Field(default=None, max_length=128)
    regression_tolerance: float = Field(default=0.0, ge=0)


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experiment_name: str
    experiment_type: str
    baseline_config_json: dict[str, Any]
    candidate_config_json: dict[str, Any]
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    conclusion: str | None
    artifact_path: str | None
    created_at: datetime


class ExperimentComparisonResponse(BaseModel):
    experiment_id: int
    experiment_name: str
    conclusion: str
    regressions: list[dict[str, Any]]
    comparisons: list[dict[str, Any]]
    failed_cases: list[dict[str, Any]]
    artifacts: dict[str, str]
