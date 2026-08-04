"""Evaluation metrics, callback runner, and report generation."""

from app.evaluation.metrics import (
    EvaluationAggregate,
    EvaluationSample,
    EvaluationSampleMetrics,
    evaluate_sample,
    evaluate_samples,
)
from app.evaluation.reports import (
    HALLUCINATION_SCOPE,
    EvaluationReportArtifacts,
    write_evaluation_reports,
)
from app.evaluation.runner import (
    ChatCallback,
    ChatResult,
    EvaluationCase,
    EvaluationQuestionResult,
    EvaluationRunner,
    EvaluationRunResult,
    RetrievalCallback,
    RetrievalResult,
    RetrievedItem,
)

__all__ = [
    "HALLUCINATION_SCOPE",
    "ChatCallback",
    "ChatResult",
    "EvaluationAggregate",
    "EvaluationCase",
    "EvaluationQuestionResult",
    "EvaluationReportArtifacts",
    "EvaluationRunResult",
    "EvaluationRunner",
    "EvaluationSample",
    "EvaluationSampleMetrics",
    "RetrievalCallback",
    "RetrievalResult",
    "RetrievedItem",
    "evaluate_sample",
    "evaluate_samples",
    "write_evaluation_reports",
]
