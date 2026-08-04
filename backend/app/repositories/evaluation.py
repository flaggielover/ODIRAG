from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataLineage, EvaluationQuestion, EvaluationRun, Experiment


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_questions(
        self, questions: Sequence[EvaluationQuestion]
    ) -> list[EvaluationQuestion]:
        if not questions:
            return []
        identifiers = [question.question_id for question in questions]
        result = await self.session.execute(
            select(EvaluationQuestion).where(EvaluationQuestion.question_id.in_(identifiers))
        )
        existing = {question.question_id: question for question in result.scalars()}
        saved: list[EvaluationQuestion] = []
        for incoming in questions:
            current = existing.get(incoming.question_id)
            if current is None:
                self.session.add(incoming)
                saved.append(incoming)
                continue
            for field in _QUESTION_FIELDS:
                setattr(current, field, getattr(incoming, field))
            saved.append(current)
        await self.session.flush()
        return saved

    async def list_verified_questions(
        self,
        *,
        question_ids: Sequence[str] = (),
        category: str | None = None,
    ) -> list[EvaluationQuestion]:
        statement = select(EvaluationQuestion).where(EvaluationQuestion.verified.is_(True))
        if question_ids:
            statement = statement.where(EvaluationQuestion.question_id.in_(question_ids))
        if category is not None:
            statement = statement.where(EvaluationQuestion.category == category)
        statement = statement.order_by(EvaluationQuestion.question_id)
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def create_run(self, run: EvaluationRun) -> EvaluationRun:
        self.session.add(run)
        await self.session.flush()
        return run

    async def add_lineages(self, lineages: Sequence[DataLineage]) -> None:
        if not lineages:
            return
        self.session.add_all(lineages)
        await self.session.flush()

    async def finish_run(
        self,
        run: EvaluationRun,
        *,
        aggregate: dict[str, float | int],
        average_latency_ms: float,
        result_path: str,
    ) -> EvaluationRun:
        run.finished_at = datetime.now(UTC)
        run.question_count = int(aggregate["question_count"])
        run.recall_at_1 = _decimal(aggregate["recall_at_1"])
        run.recall_at_5 = _decimal(aggregate["recall_at_5"])
        run.recall_at_10 = _decimal(aggregate["recall_at_10"])
        run.mrr = _decimal(aggregate["mrr"])
        run.ndcg = _decimal(aggregate["ndcg_at_10"])
        run.citation_accuracy = _decimal(aggregate["citation_accuracy"])
        run.refusal_accuracy = _decimal(aggregate["refusal_accuracy"])
        run.hallucination_rate = _decimal(aggregate["hallucination_rate"])
        run.average_latency = _decimal(average_latency_ms)
        run.p95_latency = _decimal(aggregate["p95_latency_ms"])
        run.average_cost = _decimal(aggregate["average_cost"])
        run.result_path = result_path
        await self.session.flush()
        return run

    async def list_runs(self, *, limit: int = 100) -> list[EvaluationRun]:
        result = await self.session.execute(
            select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(limit)
        )
        return list(result.scalars())

    async def get_run(self, run_id: int) -> EvaluationRun | None:
        return await self.session.get(EvaluationRun, run_id)

    async def commit(self) -> None:
        await self.session.commit()


class ExperimentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, experiment: Experiment) -> Experiment:
        self.session.add(experiment)
        await self.session.flush()
        return experiment

    async def list(self, *, limit: int = 100) -> list[Experiment]:
        result = await self.session.execute(
            select(Experiment).order_by(Experiment.created_at.desc()).limit(limit)
        )
        return list(result.scalars())

    async def get(self, experiment_id: int) -> Experiment | None:
        return await self.session.get(Experiment, experiment_id)

    async def start(self, experiment: Experiment) -> None:
        experiment.status = "running"
        experiment.started_at = datetime.now(UTC)
        experiment.finished_at = None
        await self.session.flush()

    async def finish(
        self,
        experiment: Experiment,
        *,
        conclusion: str,
        artifact_path: str,
        status: str = "completed",
    ) -> None:
        experiment.status = status
        experiment.finished_at = datetime.now(UTC)
        experiment.conclusion = conclusion
        experiment.artifact_path = artifact_path
        await self.session.flush()

    async def commit(self) -> None:
        await self.session.commit()


_QUESTION_FIELDS = (
    "question",
    "query_type",
    "expected_document_ids",
    "expected_chunk_ids",
    "expected_answer_points",
    "expected_filters",
    "should_refuse",
    "difficulty",
    "category",
    "created_by",
    "verified",
)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))
