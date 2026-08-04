"""Configuration, execution, comparison, and reporting for reproducible experiments."""

from app.experiments.comparison import MetricDelta, compare_metrics
from app.experiments.config import (
    ExperimentConfig,
    ExperimentConfigError,
    ExperimentVariantConfig,
    load_experiment_config,
)
from app.experiments.reports import ExperimentArtifacts, ExperimentReportWriter
from app.experiments.service import (
    CandidateFailure,
    EvaluationCaseResult,
    EvaluationOutcome,
    EvaluationRequest,
    EvaluationRunner,
    ExperimentExecutionError,
    ExperimentRunResult,
    ExperimentService,
    MetricComparison,
)

__all__ = [
    "CandidateFailure",
    "EvaluationCaseResult",
    "EvaluationOutcome",
    "EvaluationRequest",
    "EvaluationRunner",
    "ExperimentArtifacts",
    "ExperimentConfig",
    "ExperimentConfigError",
    "ExperimentExecutionError",
    "ExperimentReportWriter",
    "ExperimentRunResult",
    "ExperimentService",
    "ExperimentVariantConfig",
    "MetricComparison",
    "MetricDelta",
    "compare_metrics",
    "load_experiment_config",
]
