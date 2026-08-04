from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

_RUNNER_SPEC = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:"
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)


class ExperimentConfigError(ValueError):
    """Raised when an experiment YAML file cannot be loaded or validated."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ExperimentVariantConfig(_StrictModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    parameters: dict[str, JsonValue] = Field(min_length=1)

    @field_validator("parameters")
    @classmethod
    def reject_non_finite_parameters(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        cls._check_finite(value, "parameters")
        return value

    @classmethod
    def _check_finite(cls, value: JsonValue, path: str) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{path} must not contain non-finite numbers")
        if isinstance(value, list):
            for index, item in enumerate(value):
                cls._check_finite(item, f"{path}[{index}]")
        elif isinstance(value, dict):
            for key, item in value.items():
                cls._check_finite(item, f"{path}.{key}")


class ExperimentConfig(_StrictModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    experiment_type: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$",
    )
    dataset: str = Field(min_length=1, max_length=4096)
    output_directory: str = Field(min_length=1, max_length=4096)
    runner: str | None = None
    regression_tolerance: float = Field(default=0.0, ge=0.0)
    lower_is_better: tuple[str, ...] = (
        "latency",
        "average_latency",
        "p50_latency_ms",
        "p95_latency_ms",
        "cost",
        "average_cost",
        "hallucination_rate",
    )
    baseline: ExperimentVariantConfig
    candidate: ExperimentVariantConfig

    @field_validator("dataset", "output_directory")
    @classmethod
    def reject_blank_paths(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("runner")
    @classmethod
    def validate_runner_spec(cls, value: str | None) -> str | None:
        if value is not None and not _RUNNER_SPEC.fullmatch(value):
            raise ValueError("runner must use the trusted module:attribute format")
        return value

    @field_validator("regression_tolerance")
    @classmethod
    def reject_non_finite_tolerance(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("regression_tolerance must be finite")
        return value

    @field_validator("lower_is_better")
    @classmethod
    def validate_metric_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(name.strip() for name in value)
        if any(not name for name in normalized):
            raise ValueError("lower_is_better cannot contain blank metric names")
        if len(set(normalized)) != len(normalized):
            raise ValueError("lower_is_better cannot contain duplicate metric names")
        return normalized

    @model_validator(mode="after")
    def require_distinct_variants(self) -> ExperimentConfig:
        if self.baseline.name == self.candidate.name:
            raise ValueError("baseline and candidate names must be different")
        return self


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path)
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ExperimentConfigError(f"cannot load experiment config {config_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExperimentConfigError("experiment config must contain a YAML mapping")
    try:
        return ExperimentConfig.model_validate(payload)
    except ValidationError as exc:
        raise ExperimentConfigError(f"invalid experiment config {config_path}: {exc}") from exc
