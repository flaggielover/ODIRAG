from __future__ import annotations

# ruff: noqa: I001

import argparse
import asyncio
import importlib
import json
import os
import sys
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.experiments import (
    EvaluationRunner,
    ExperimentConfigError,
    ExperimentExecutionError,
    ExperimentReportWriter,
    ExperimentService,
    load_experiment_config,
)


class RunnerLoadError(RuntimeError):
    """Raised when a trusted evaluation runner plugin cannot be constructed."""


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run baseline and candidate evaluations and generate experiment artifacts"
    )
    parser.add_argument(
        "--config", required=True, type=Path, help="Experiment YAML file"
    )
    parser.add_argument(
        "--runner",
        help=(
            "Trusted evaluation runner object, class, or zero-argument factory in "
            "module:attribute form; overrides YAML and ODIRAG_EXPERIMENT_RUNNER"
        ),
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        help="Override the artifact directory from the YAML file",
    )
    return parser.parse_args()


def _load_runner(specification: str) -> EvaluationRunner:
    module_name, separator, attribute_path = specification.partition(":")
    if not separator or not module_name or not attribute_path:
        raise RunnerLoadError("runner must use module:attribute format")
    try:
        target: object = importlib.import_module(module_name)
        for attribute in attribute_path.split("."):
            target = getattr(target, attribute)
        if isinstance(target, type) or (
            callable(target) and not callable(getattr(target, "run", None))
        ):
            candidate = target()
        else:
            candidate = target
    except (AttributeError, ImportError, TypeError) as exc:
        raise RunnerLoadError(
            f"cannot load evaluation runner {specification!r}: {exc}"
        ) from exc
    if not callable(getattr(candidate, "run", None)):
        raise RunnerLoadError(
            f"evaluation runner {specification!r} must expose an async run(request) method"
        )
    return cast(EvaluationRunner, candidate)


async def _run(arguments: argparse.Namespace) -> dict[str, str | bool]:
    config_path = arguments.config.resolve()
    config = load_experiment_config(config_path)
    runner_spec = (
        arguments.runner or config.runner or os.environ.get("ODIRAG_EXPERIMENT_RUNNER")
    )
    if not runner_spec:
        raise RunnerLoadError(
            "no evaluation runner configured; pass --runner module:attribute, set "
            "runner in the YAML file, or set ODIRAG_EXPERIMENT_RUNNER"
        )
    output_directory = arguments.output_directory or Path(config.output_directory)
    if not output_directory.is_absolute():
        output_directory = (REPOSITORY_ROOT / output_directory).resolve()

    result = await ExperimentService(_load_runner(runner_spec)).run(config)
    artifacts = ExperimentReportWriter().write(result, output_directory)
    return {
        "has_regression": result.has_regression,
        "result_json": str(artifacts.result_json),
        "markdown_report": str(artifacts.markdown_report),
        "chart_data_json": str(artifacts.chart_data_json),
    }


def main() -> None:
    try:
        payload = asyncio.run(_run(_arguments()))
    except (ExperimentConfigError, ExperimentExecutionError, RunnerLoadError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
