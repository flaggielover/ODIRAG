from __future__ import annotations

import copy
import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from app.experiments.comparison import compare_metrics
from app.experiments.config import ExperimentConfig, ExperimentVariantConfig


class _ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluationRequest(_ResultModel):
    experiment_name: str
    experiment_type: str
    dataset: str
    role: Literal["baseline", "candidate"]
    variant_name: str
    parameters: dict[str, JsonValue]


class EvaluationCaseResult(_ResultModel):
    case_id: str = Field(min_length=1, max_length=255)
    passed: bool
    failure_reason: str | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_failure_reason(self) -> EvaluationCaseResult:
        if not self.passed and not self.failure_reason:
            raise ValueError("failed evaluation cases require failure_reason")
        return self


class EvaluationOutcome(_ResultModel):
    metrics: dict[str, float] = Field(min_length=1)
    cases: tuple[EvaluationCaseResult, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metrics", mode="before")
    @classmethod
    def validate_metrics(cls, value: object) -> dict[str, float]:
        if not isinstance(value, dict) or not value:
            raise ValueError("metrics must be a non-empty mapping")
        normalized: dict[str, float] = {}
        for raw_name, raw_value in value.items():
            if not isinstance(raw_name, str) or not raw_name.strip():
                raise ValueError("metric names must be non-empty strings")
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise ValueError(f"metric {raw_name!r} must be numeric")
            numeric = float(raw_value)
            if not math.isfinite(numeric):
                raise ValueError(f"metric {raw_name!r} must be finite")
            normalized[raw_name.strip()] = numeric
        if len(normalized) != len(value):
            raise ValueError("metric names must be unique after trimming")
        return normalized

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> EvaluationOutcome:
        case_ids = [case.case_id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("evaluation case IDs must be unique")
        return self


class MetricComparison(_ResultModel):
    name: str
    baseline: float
    candidate: float
    delta: float
    regression: bool


class CandidateFailure(_ResultModel):
    case_id: str
    failure_reason: str
    baseline_passed: bool | None
    new_regression: bool
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ExperimentRunResult(_ResultModel):
    config: ExperimentConfig
    started_at: datetime
    finished_at: datetime
    baseline: EvaluationOutcome
    candidate: EvaluationOutcome
    comparisons: tuple[MetricComparison, ...]
    candidate_failures: tuple[CandidateFailure, ...]
    has_regression: bool


class EvaluationRunner(Protocol):
    async def run(self, request: EvaluationRequest) -> EvaluationOutcome: ...


class ExperimentExecutionError(RuntimeError):
    """Raised when a configured evaluation runner cannot complete an experiment variant."""


class ExperimentService:
    def __init__(
        self,
        runner: EvaluationRunner,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._runner = runner
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run(self, config: ExperimentConfig) -> ExperimentRunResult:
        started_at = self._clock()
        baseline = await self._evaluate(config, config.baseline, "baseline")
        candidate = await self._evaluate(config, config.candidate, "candidate")
        self._validate_case_sets(baseline, candidate)
        try:
            deltas = compare_metrics(
                baseline.metrics,
                candidate.metrics,
                lower_is_better=frozenset(config.lower_is_better),
                tolerance=config.regression_tolerance,
            )
        except ValueError as exc:
            raise ExperimentExecutionError(
                f"baseline and candidate metrics are not comparable: {exc}"
            ) from exc
        comparisons = tuple(
            MetricComparison(
                name=delta.name,
                baseline=delta.baseline,
                candidate=delta.candidate,
                delta=delta.delta,
                regression=delta.regression,
            )
            for delta in deltas
        )
        failures = self._candidate_failures(baseline, candidate)
        has_regression = any(item.regression for item in comparisons) or any(
            failure.new_regression for failure in failures
        )
        return ExperimentRunResult(
            config=config,
            started_at=started_at,
            finished_at=self._clock(),
            baseline=baseline,
            candidate=candidate,
            comparisons=comparisons,
            candidate_failures=failures,
            has_regression=has_regression,
        )

    async def _evaluate(
        self,
        config: ExperimentConfig,
        variant: ExperimentVariantConfig,
        role: Literal["baseline", "candidate"],
    ) -> EvaluationOutcome:
        request = EvaluationRequest(
            experiment_name=config.name,
            experiment_type=config.experiment_type,
            dataset=config.dataset,
            role=role,
            variant_name=variant.name,
            parameters=copy.deepcopy(variant.parameters),
        )
        try:
            result = await self._runner.run(request)
        except Exception as exc:
            raise ExperimentExecutionError(
                f"{role} evaluation {variant.name!r} failed: {exc.__class__.__name__}: {exc}"
            ) from exc
        if not isinstance(result, EvaluationOutcome):
            raise ExperimentExecutionError(
                f"{role} evaluation {variant.name!r} returned {type(result).__name__}; "
                "expected EvaluationOutcome"
            )
        return result

    @staticmethod
    def _validate_case_sets(
        baseline: EvaluationOutcome,
        candidate: EvaluationOutcome,
    ) -> None:
        baseline_ids = {case.case_id for case in baseline.cases}
        candidate_ids = {case.case_id for case in candidate.cases}
        if baseline_ids != candidate_ids:
            missing = sorted(baseline_ids - candidate_ids)
            added = sorted(candidate_ids - baseline_ids)
            raise ExperimentExecutionError(
                "baseline and candidate case IDs differ: "
                f"missing_from_candidate={missing}, candidate_only={added}"
            )

    @staticmethod
    def _candidate_failures(
        baseline: EvaluationOutcome,
        candidate: EvaluationOutcome,
    ) -> tuple[CandidateFailure, ...]:
        baseline_cases = {case.case_id: case for case in baseline.cases}
        failures: list[CandidateFailure] = []
        for case in candidate.cases:
            if case.passed:
                continue
            baseline_case = baseline_cases.get(case.case_id)
            baseline_passed = baseline_case.passed if baseline_case is not None else None
            failures.append(
                CandidateFailure(
                    case_id=case.case_id,
                    failure_reason=case.failure_reason or "unspecified failure",
                    baseline_passed=baseline_passed,
                    new_regression=baseline_passed is not False,
                    details=case.details,
                )
            )
        return tuple(sorted(failures, key=lambda failure: failure.case_id))
