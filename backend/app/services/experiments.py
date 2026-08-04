from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import Settings
from app.experiments import (
    ExperimentConfig,
    ExperimentExecutionError,
    ExperimentReportWriter,
    ExperimentService,
    ExperimentVariantConfig,
)
from app.experiments.odirag import ODIRAGVariantEvaluationRunner
from app.models import Experiment
from app.repositories.evaluation import ExperimentRepository
from app.runtime import ApplicationRuntime, resolve_runtime_path
from app.schemas.evaluation import EvaluationRunRequest
from app.schemas.experiment import ExperimentCreateRequest, ExperimentRunRequest


class ExperimentApplicationService:
    def __init__(
        self,
        repository: ExperimentRepository,
        *,
        settings: Settings,
        runtime: ApplicationRuntime,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.runtime = runtime
        self.artifact_root = resolve_runtime_path(settings.experiment_artifact_dir).resolve()

    async def create(self, request: ExperimentCreateRequest) -> Experiment:
        experiment = await self.repository.create(
            Experiment(
                experiment_name=request.experiment_name,
                experiment_type=request.experiment_type,
                baseline_config_json=request.baseline_config,
                candidate_config_json=request.candidate_config,
                status="pending",
            )
        )
        await self.repository.commit()
        return experiment

    async def list(self, *, limit: int = 100) -> list[Experiment]:
        return await self.repository.list(limit=limit)

    async def get(self, experiment_id: int) -> Experiment | None:
        return await self.repository.get(experiment_id)

    async def run(
        self,
        experiment: Experiment,
        request: ExperimentRunRequest,
    ) -> Experiment:
        await self.repository.start(experiment)
        await self.repository.commit()
        output_dir = self.artifact_root / str(experiment.id)
        config = ExperimentConfig(
            name=experiment.experiment_name,
            experiment_type=experiment.experiment_type,
            dataset=(
                f"database:verified:{request.category}" if request.category else "database:verified"
            ),
            output_directory=str(output_dir),
            regression_tolerance=request.regression_tolerance,
            baseline=ExperimentVariantConfig(
                name="baseline",
                parameters=experiment.baseline_config_json,
            ),
            candidate=ExperimentVariantConfig(
                name="candidate",
                parameters=experiment.candidate_config_json,
            ),
        )
        evaluation_request = EvaluationRunRequest(
            run_name=experiment.experiment_name,
            question_ids=request.question_ids,
            questions=request.questions,
            category=request.category,
        )
        runner = ODIRAGVariantEvaluationRunner(
            self.repository.session,
            self.settings,
            self.runtime,
            evaluation_request,
            experiment_id=experiment.id,
        )
        try:
            result = await ExperimentService(runner).run(config)
            artifacts = ExperimentReportWriter().write(result, output_dir)
        except Exception as exc:
            await self.repository.finish(
                experiment,
                conclusion=f"Experiment failed: {exc.__class__.__name__}: {exc}",
                artifact_path=str(output_dir.resolve()),
                status="failed",
            )
            await self.repository.commit()
            raise
        conclusion = _conclusion(result.has_regression, len(result.candidate_failures))
        await self.repository.finish(
            experiment,
            conclusion=conclusion,
            artifact_path=str(artifacts.result_json.resolve()),
        )
        await self.repository.commit()
        return experiment

    async def compare(self, experiment: Experiment) -> dict[str, Any]:
        if experiment.status != "completed" or not experiment.artifact_path:
            raise ExperimentExecutionError("experiment does not have a completed comparison")
        report_path = _resolve(experiment.artifact_path)
        if not report_path.is_relative_to(self.artifact_root):
            raise ExperimentExecutionError(
                "experiment report path is outside the configured artifact root"
            )
        payload = _load_json(report_path)
        comparisons = payload.get("comparisons", [])
        failures = payload.get("candidate_failures", [])
        if not isinstance(comparisons, list) or not isinstance(failures, list):
            raise ExperimentExecutionError("experiment report has invalid comparison data")
        payload.update(
            {
                "experiment_id": experiment.id,
                "experiment_name": experiment.experiment_name,
                "conclusion": experiment.conclusion or "",
                "regressions": [
                    item
                    for item in comparisons
                    if isinstance(item, dict) and item.get("regression") is True
                ],
                "failed_cases": failures,
                "artifacts": _artifact_paths(report_path.parent),
            }
        )
        return payload


def _conclusion(has_regression: bool, failed_case_count: int) -> str:
    if has_regression:
        return (
            "Regression detected. Review regressed metrics and "
            f"{failed_case_count} candidate failed case(s) before promotion."
        )
    return "No configured metric or failed-case regression was detected."


def _resolve(path: str) -> Path:
    return Path(path).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExperimentExecutionError(f"experiment report is unavailable: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExperimentExecutionError("experiment report payload must be an object")
    return payload


def _artifact_paths(output_dir: Path) -> dict[str, str]:
    names = {
        "json": "experiment.json",
        "markdown": "report.md",
        "chart_data": "chart_data.json",
    }
    return {
        key: str((output_dir / filename).resolve())
        for key, filename in names.items()
        if (output_dir / filename).is_file()
    }
