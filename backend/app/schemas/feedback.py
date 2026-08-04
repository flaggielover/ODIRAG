from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FeedbackType = Literal[
    "helpful",
    "not_helpful",
    "incorrect_citation",
    "missing_document",
    "incomplete_answer",
    "should_refuse",
    "should_not_refuse",
]


class FeedbackCreate(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)
    rating: int | None = Field(default=None, ge=1, le=5)
    feedback_type: FeedbackType
    comment: str | None = Field(default=None, max_length=4000)
    expected_document_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_expected_document_when_needed(self) -> FeedbackCreate:
        if (
            self.feedback_type in {"missing_document", "should_not_refuse"}
            and self.expected_document_id is None
        ):
            raise ValueError(f"{self.feedback_type} feedback requires expected_document_id")
        return self


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trace_id: str
    rating: int | None
    feedback_type: FeedbackType
    comment: str | None
    expected_document_id: int | None
    resolved: bool
    converted_to_evaluation: bool
    created_at: datetime
