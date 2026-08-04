from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.experiments import (
    EvaluationCaseResult,
    EvaluationOutcome,
    EvaluationRequest,
    ExperimentConfig,
    ExperimentConfigError,
    ExperimentExecutionError,
    ExperimentReportWriter,
    ExperimentService,
    ExperimentVariantConfig,
    load_experiment_config,
)


class RecordingEvaluationRunner:
    def __init__(self) -> None:
        self.requests: list[EvaluationRequest] = []

    async def run(self, request: EvaluationRequest) -> EvaluationOutcome:
        self.requests.append(request)
        if request.role == "baseline":
            return EvaluationOutcome(
                metrics={"recall_at_5": 0.9, "p95_latency_ms": 100.0},
                cases=(
                    EvaluationCaseResult(case_id="q-1", passed=True),
                    EvaluationCaseResult(
                        case_id="q-2",
                        passed=False,
                        failure_reason="missing citation",
                    ),
                ),
            )
        return EvaluationOutcome(
            metrics={"recall_at_5": 0.8, "p95_latency_ms": 120.0},
            cases=(
                EvaluationCaseResult(
                    case_id="q-1",
                    passed=False,
                    failure_reason="relevant document not retrieved",
                    details={"rank": None},
                ),
                EvaluationCaseResult(
                    case_id="q-2",
                    passed=False,
                    failure_reason="missing citation",
                ),
            ),
        )


class MismatchedMetricRunner:
    async def run(self, request: EvaluationRequest) -> EvaluationOutcome:
        metric_name = "recall_at_5" if request.role == "baseline" else "mrr"
        return EvaluationOutcome(metrics={metric_name: 0.8})


@pytest.fixture
def workspace_tmp_path() -> Iterator[Path]:
    root = Path(__file__).resolve().parents[2] / ".tmp" / "phase10-tests"
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        name="chunk_600_vs_800",
        experiment_type="chunking",
        dataset="benchmark-v1",
        output_directory="data/experiments/runs/chunk_600_vs_800",
        lower_is_better=("p95_latency_ms",),
        baseline=ExperimentVariantConfig(
            name="chunk_600",
            parameters={"chunking": {"target_chars": 600}},
        ),
        candidate=ExperimentVariantConfig(
            name="chunk_800",
            parameters={"chunking": {"target_chars": 800}},
        ),
    )


def test_load_experiment_config_is_strict(workspace_tmp_path: Path) -> None:
    config_path = workspace_tmp_path / "experiment.yaml"
    config_path.write_text(
        """
schema_version: 1
name: invalid_extra_field
experiment_type: retrieval
dataset: benchmark-v1
output_directory: output
unexpected: rejected
baseline:
  name: baseline
  parameters:
    top_k: 5
candidate:
  name: candidate
  parameters:
    top_k: 10
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(ExperimentConfigError, match="unexpected"):
        load_experiment_config(config_path)


def test_config_rejects_identical_variant_names_and_non_finite_metrics() -> None:
    with pytest.raises(ValidationError, match="must be different"):
        ExperimentConfig(
            name="same_variants",
            experiment_type="retrieval",
            dataset="benchmark-v1",
            output_directory="output",
            baseline=ExperimentVariantConfig(name="same", parameters={"top_k": 5}),
            candidate=ExperimentVariantConfig(name="same", parameters={"top_k": 10}),
        )
    with pytest.raises(ValidationError, match="must be finite"):
        EvaluationOutcome(metrics={"recall_at_5": float("nan")})
    with pytest.raises(ValidationError, match="non-finite"):
        ExperimentVariantConfig(
            name="invalid",
            parameters={"threshold": float("inf")},
        )


@pytest.mark.asyncio
async def test_service_runs_both_variants_and_detects_regressions() -> None:
    runner = RecordingEvaluationRunner()
    started = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
    times = iter((started, started + timedelta(seconds=2)))

    result = await ExperimentService(runner, clock=lambda: next(times)).run(_config())

    assert [request.role for request in runner.requests] == ["baseline", "candidate"]
    assert [item.name for item in result.comparisons if item.regression] == [
        "p95_latency_ms",
        "recall_at_5",
    ]
    assert result.has_regression
    assert [(failure.case_id, failure.new_regression) for failure in result.candidate_failures] == [
        ("q-1", True),
        ("q-2", False),
    ]


@pytest.mark.asyncio
async def test_service_rejects_mismatched_metric_sets() -> None:
    with pytest.raises(ExperimentExecutionError, match="not comparable"):
        await ExperimentService(MismatchedMetricRunner()).run(_config())


@pytest.mark.asyncio
async def test_reports_write_json_markdown_and_chart_data(workspace_tmp_path: Path) -> None:
    runner = RecordingEvaluationRunner()
    result = await ExperimentService(runner).run(_config())

    artifacts = ExperimentReportWriter().write(result, workspace_tmp_path)

    full_report = json.loads(artifacts.result_json.read_text(encoding="utf-8"))
    chart_data = json.loads(artifacts.chart_data_json.read_text(encoding="utf-8"))
    markdown = artifacts.markdown_report.read_text(encoding="utf-8")
    assert full_report["config"]["name"] == "chunk_600_vs_800"
    assert chart_data["failures"]["new_candidate_regressions"] == 1
    assert chart_data["metrics"][0]["metric"] == "p95_latency_ms"
    assert "REGRESSION DETECTED" in markdown
    assert "relevant document not retrieved" in markdown


def test_repository_sample_config_is_valid() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    config = load_experiment_config(
        repository_root / "data" / "experiments" / "chunk_600_vs_800.yaml"
    )
    assert config.runner == "app.experiments.demo:DemoDatasetExperimentRunner"
    assert config.dataset == "data/evaluation/demo_benchmark.yaml"
    assert config.baseline.parameters["chunking"] == {
        "target_chars": 600,
        "min_chars": 160,
        "max_chars": 900,
        "overlap_chars": 100,
    }
    assert config.candidate.parameters["chunking"] == {
        "target_chars": 800,
        "min_chars": 160,
        "max_chars": 1200,
        "overlap_chars": 120,
    }
