from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings
from app.database.session import DatabaseManager
from app.experiments.odirag import ODIRAGVariantEvaluationRunner
from app.experiments.service import EvaluationOutcome, EvaluationRequest
from app.models import Document, Experiment, Source, SourceColumn
from app.runtime import build_application_runtime
from app.schemas.evaluation import EvaluationQuestionInput, EvaluationRunRequest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DemoSource(_StrictModel):
    source_key: str
    name: str
    domain: str
    homepage_url: str
    official_status: str = "official"
    region: str | None = None
    city: str | None = None


class DemoDocument(_StrictModel):
    document_id: str
    title: str
    source_url: str
    content: str
    publish_date: date | None = None
    issuing_authority: str | None = None
    document_number: str | None = None
    region: str | None = None
    city: str | None = None
    document_type: str | None = None


class DemoDataset(_StrictModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    source: DemoSource
    documents: list[DemoDocument] = Field(min_length=1)
    questions: list[EvaluationQuestionInput] = Field(min_length=1)


class DemoDatasetExperimentRunner:
    """Run a repository-local YAML benchmark without external services."""

    async def run(self, request: EvaluationRequest) -> EvaluationOutcome:
        dataset_path = _dataset_path(request.dataset)
        dataset = _load_dataset(dataset_path)
        temp_path = _working_directory()
        settings = Settings(
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            auto_create_schema=False,
            bootstrap_admin=False,
            health_check_qdrant=False,
            embedding_provider="deterministic",
            embedding_cache_provider="memory",
            embedding_dimensions=32,
            vector_store_provider="memory",
            rerank_provider="deterministic",
            answer_provider="extractive",
            chunking_config_path=_REPOSITORY_ROOT / "config" / "chunking.yaml",
            grounded_answer_prompt_path=(
                _REPOSITORY_ROOT / "config" / "prompts" / "grounded_answer_v1.txt"
            ),
            bm25_snapshot_path=temp_path / "bm25.json",
            evaluation_artifact_dir=temp_path / "evaluation-runs",
            experiment_artifact_dir=temp_path / "experiment-runs",
        )
        database = DatabaseManager(settings)
        try:
            await database.create_schema()
            runtime = build_application_runtime(settings)
            async with database.session_factory() as session:
                experiment_id = await _seed(session, dataset, request)
                runner = ODIRAGVariantEvaluationRunner(
                    session,
                    settings,
                    runtime,
                    EvaluationRunRequest(
                        run_name=request.experiment_name,
                        questions=dataset.questions,
                    ),
                    experiment_id=experiment_id,
                )
                outcome = await runner.run(request)
        finally:
            await database.dispose()
        return outcome.model_copy(
            update={
                "metadata": {
                    **outcome.metadata,
                    "dataset": str(dataset_path),
                    "evaluation_workspace": str(temp_path),
                }
            }
        )


async def _seed(session: Any, dataset: DemoDataset, request: EvaluationRequest) -> int:
    source = Source(
        source_key=dataset.source.source_key,
        name=dataset.source.name,
        domain=dataset.source.domain,
        homepage_url=dataset.source.homepage_url,
        official_status=dataset.source.official_status,
        region=dataset.source.region,
        city=dataset.source.city,
    )
    column = SourceColumn(
        source=source,
        column_key="demo",
        column_name="Demo policies",
        column_url=dataset.source.homepage_url,
        request_interval_seconds=0,
    )
    session.add_all(
        [
            Document(
                document_id=item.document_id,
                source=source,
                source_column=column,
                title=item.title,
                source_url=item.source_url,
                publish_date=item.publish_date,
                issuing_authority=item.issuing_authority,
                document_number=item.document_number,
                region=item.region,
                city=item.city,
                document_type=item.document_type,
                content=item.content,
                content_hash=hashlib.sha256(item.content.encode()).hexdigest(),
                word_count=len(item.content.split()),
                final_status="approved",
                index_status="pending",
                version=1,
            )
            for item in dataset.documents
        ]
    )
    experiment = Experiment(
        experiment_name=request.experiment_name,
        experiment_type=request.experiment_type,
        baseline_config_json={"role": request.role},
        candidate_config_json={"variant": request.variant_name},
        status="running",
    )
    session.add(experiment)
    await session.commit()
    return int(experiment.id)


def _dataset_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (_REPOSITORY_ROOT / path).resolve()


def _load_dataset(path: Path) -> DemoDataset:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return DemoDataset.model_validate(payload)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as exc:
        raise ValueError(f"cannot load demo evaluation dataset {path}: {exc}") from exc


def _working_directory() -> Path:
    path = _REPOSITORY_ROOT / "backend" / ".test-data" / "experiment-runs" / str(uuid.uuid4())
    path.mkdir(parents=True, exist_ok=True)
    return path
