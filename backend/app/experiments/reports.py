from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue

from app.experiments.service import ExperimentRunResult


@dataclass(frozen=True, slots=True)
class ExperimentArtifacts:
    result_json: Path
    markdown_report: Path
    chart_data_json: Path


class ExperimentReportWriter:
    def write(
        self,
        result: ExperimentRunResult,
        output_directory: str | Path,
    ) -> ExperimentArtifacts:
        output_path = Path(output_directory)
        output_path.mkdir(parents=True, exist_ok=True)
        result_json = output_path / "experiment.json"
        markdown_report = output_path / "report.md"
        chart_data_json = output_path / "chart_data.json"

        self._write_json(result_json, result.model_dump(mode="json"))
        self._write_text(markdown_report, self._markdown(result))
        self._write_json(chart_data_json, self._chart_data(result))
        return ExperimentArtifacts(result_json, markdown_report, chart_data_json)

    @staticmethod
    def _chart_data(result: ExperimentRunResult) -> dict[str, JsonValue]:
        lower_is_better = set(result.config.lower_is_better)
        metrics: list[JsonValue] = []
        for item in result.comparisons:
            metric: dict[str, JsonValue] = {
                "metric": item.name,
                "baseline": item.baseline,
                "candidate": item.candidate,
                "delta": item.delta,
                "direction": (
                    "lower_is_better" if item.name in lower_is_better else "higher_is_better"
                ),
                "regression": item.regression,
            }
            metrics.append(metric)
        baseline_failure_count = sum(not case.passed for case in result.baseline.cases)
        candidate_failure_count = len(result.candidate_failures)
        failure_counts: dict[str, JsonValue] = {
            "baseline": baseline_failure_count,
            "candidate": candidate_failure_count,
            "new_candidate_regressions": sum(
                failure.new_regression for failure in result.candidate_failures
            ),
        }
        return {
            "schema_version": 1,
            "experiment_name": result.config.name,
            "has_regression": result.has_regression,
            "metrics": metrics,
            "failures": failure_counts,
        }

    @classmethod
    def _markdown(cls, result: ExperimentRunResult) -> str:
        status = "REGRESSION DETECTED" if result.has_regression else "NO REGRESSION DETECTED"
        lines = [
            f"# Experiment: {cls._escape(result.config.name)}",
            "",
            f"- Status: **{status}**",
            f"- Type: `{cls._escape(result.config.experiment_type)}`",
            f"- Dataset: `{cls._escape(result.config.dataset)}`",
            f"- Baseline: `{cls._escape(result.config.baseline.name)}`",
            f"- Candidate: `{cls._escape(result.config.candidate.name)}`",
            f"- Started: `{result.started_at.isoformat()}`",
            f"- Finished: `{result.finished_at.isoformat()}`",
            "",
            "## Metric Comparison",
            "",
            "| Metric | Baseline | Candidate | Delta | Regression |",
            "| --- | ---: | ---: | ---: | :---: |",
        ]
        lines.extend(
            f"| {cls._escape(item.name)} | {item.baseline:.6g} | {item.candidate:.6g} | "
            f"{item.delta:+.6g} | {'yes' if item.regression else 'no'} |"
            for item in result.comparisons
        )
        lines.extend(["", "## Candidate Failed Cases", ""])
        if not result.candidate_failures:
            lines.append("No candidate cases failed.")
        else:
            lines.extend(
                [
                    "| Case | Reason | Baseline passed | New regression |",
                    "| --- | --- | :---: | :---: |",
                ]
            )
            for failure in result.candidate_failures:
                baseline_passed = (
                    "unknown"
                    if failure.baseline_passed is None
                    else str(failure.baseline_passed).lower()
                )
                lines.append(
                    f"| {cls._escape(failure.case_id)} | "
                    f"{cls._escape(failure.failure_reason)} | {baseline_passed} | "
                    f"{'yes' if failure.new_regression else 'no'} |"
                )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")

    @classmethod
    def _write_json(cls, path: Path, payload: object) -> None:
        content = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        cls._write_text(path, content + "\n")

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
            temporary_path.replace(path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
