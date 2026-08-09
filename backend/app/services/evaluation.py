from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from app.evaluation import (
    ChatResult,
    EvaluationCase,
    EvaluationRunner,
    EvaluationRunResult,
    RetrievalResult,
    RetrievedItem,
    write_evaluation_reports,
)
from app.models import DataLineage, EvaluationQuestion, EvaluationRun
from app.repositories.evaluation import EvaluationRepository
from app.repositories.observability import ObservabilityRepository
from app.schemas.evaluation import EvaluationQuestionInput, EvaluationRunRequest
from app.services.chat import ChatAnswer, ChatService


class EvaluationApplicationService:
    def __init__(
        self,
        repository: EvaluationRepository,
        chat_service: ChatService,
        *,
        artifact_root: Path,
        embedding_model: str,
        rerank_model: str | None,
        default_retrieval_version: str,
        default_prompt_version: str,
    ) -> None:
        self.repository = repository
        self.chat_service = chat_service
        self.artifact_root = artifact_root.resolve()
        self.embedding_model = embedding_model
        self.rerank_model = rerank_model
        self.default_retrieval_version = default_retrieval_version
        self.default_prompt_version = default_prompt_version

    async def run(
        self,
        request: EvaluationRunRequest,
        *,
        experiment_id: int | None = None,
        run_metadata: dict[str, object] | None = None,
        additional_filters: dict[str, Any] | None = None,
    ) -> EvaluationRun:
        inline_ids = await self._save_inline_questions(request.questions)
        selected_ids = tuple(dict.fromkeys([*request.question_ids, *inline_ids]))
        questions = await self.repository.list_verified_questions(
            question_ids=selected_ids,
            category=request.category,
        )
        if selected_ids:
            found = {question.question_id for question in questions}
            missing = [identifier for identifier in selected_ids if identifier not in found]
            if missing:
                raise ValueError(f"verified evaluation questions not found: {missing}")
        if not questions:
            raise ValueError("no verified evaluation questions matched the request")

        run = await self.repository.create_run(
            EvaluationRun(
                run_name=request.run_name,
                experiment_id=experiment_id,
                retrieval_version=(request.retrieval_version or self.default_retrieval_version),
                prompt_version=request.prompt_version or self.default_prompt_version,
                embedding_model=self.embedding_model,
                rerank_model=self.rerank_model,
                top_k=request.top_k,
                started_at=_utc_now(),
            )
        )
        await self.repository.commit()

        adapter = _ChatEvaluationAdapter(self.chat_service)
        result = await EvaluationRunner(adapter.retrieve, adapter.chat).run(
            [_case(question, additional_filters) for question in questions],
            run_name=request.run_name,
            metadata={
                "evaluation_run_id": run.id,
                "retrieval_version": run.retrieval_version or "",
                "prompt_version": run.prompt_version or "",
                "embedding_model": run.embedding_model or "",
                "rerank_model": run.rerank_model or "",
                **(run_metadata or {}),
            },
        )
        output_dir = self.artifact_root / str(run.id)
        artifacts = write_evaluation_reports(result, output_dir)
        await self._record_lineage(run.id, result)
        aggregate = asdict(result.aggregate)
        average_latency = mean(question.sample.latency_ms for question in result.questions)
        await self.repository.finish_run(
            run,
            aggregate=aggregate,
            average_latency_ms=average_latency,
            result_path=str(artifacts.json_path.resolve()),
        )
        await self.repository.commit()
        return run

    async def list_runs(self, *, limit: int = 100) -> list[EvaluationRun]:
        return await self.repository.list_runs(limit=limit)

    async def get_run(self, run_id: int) -> EvaluationRun | None:
        return await self.repository.get_run(run_id)

    async def report(self, run: EvaluationRun) -> dict[str, Any]:
        if not run.result_path:
            raise ValueError("evaluation run does not have a completed report")
        report_path = _resolved_path(run.result_path)
        if not report_path.is_relative_to(self.artifact_root):
            raise ValueError("evaluation report path is outside the configured artifact root")
        payload = _load_report(report_path)
        if not isinstance(payload, dict):
            raise ValueError("evaluation report payload must be an object")
        payload["run_id"] = run.id
        payload["artifacts"] = _artifact_paths(report_path.parent)
        return payload

    async def _save_inline_questions(self, questions: list[EvaluationQuestionInput]) -> list[str]:
        if not questions:
            return []
        models = [_question_model(question) for question in questions]
        await self.repository.upsert_questions(models)
        await self.repository.commit()
        return [question.question_id for question in questions]

    async def _record_lineage(
        self,
        evaluation_run_id: int,
        result: EvaluationRunResult,
    ) -> None:
        chunk_ids = tuple(
            dict.fromkeys(
                chunk_id
                for question in result.questions
                for chunk_id in question.sample.retrieved_ids
                if chunk_id
            )
        )
        observability = ObservabilityRepository(self.repository.session)
        lineages: list[DataLineage] = []
        for chunk_id in chunk_ids:
            context = await observability.citation_lineage(chunk_id)
            if context is None:
                continue
            lineages.append(
                DataLineage(
                    lineage_id=str(uuid.uuid4()),
                    source_id=context.source.id if context.source is not None else None,
                    crawl_task_id=(
                        context.crawl_task.id if context.crawl_task is not None else None
                    ),
                    document_id=context.document.id,
                    document_version_id=(
                        context.document_version.id
                        if context.document_version is not None
                        else None
                    ),
                    attachment_id=context.chunk.attachment_id,
                    chunk_id=context.chunk.id,
                    vector_point_id=context.chunk.chunk_id,
                    evaluation_run_id=evaluation_run_id,
                )
            )
        await self.repository.add_lineages(lineages)


class _ChatEvaluationAdapter:
    def __init__(self, service: ChatService) -> None:
        self.service = service
        self._answers: dict[str, tuple[ChatAnswer, int, float]] = {}

    async def retrieve(self, case: EvaluationCase) -> RetrievalResult:
        answer = await self.service.answer(
            case.question,
            explicit_filters=dict(case.expected_filters),
        )
        stored_trace = await self.service.get_trace(answer.trace_id)
        token_count = _token_count(stored_trace.token_usage_json if stored_trace else {})
        cost = float(stored_trace.cost) if stored_trace is not None else 0.0
        self._answers[case.question_id] = (answer, token_count, cost)
        retrieval_trace = answer.retrieval_trace
        hits = retrieval_trace.final_results if retrieval_trace is not None else ()
        return RetrievalResult(
            items=tuple(
                RetrievedItem(
                    document_id=hit.document_id,
                    chunk_id=hit.chunk_id,
                    score=hit.score,
                    metadata=hit.metadata,
                )
                for hit in hits
            ),
            latency_ms=(
                float(stored_trace.latency_ms)
                if stored_trace is not None
                else (
                    retrieval_trace.timings_ms.get("total", 0.0)
                    if retrieval_trace is not None
                    else 0.0
                )
            ),
            trace={
                "trace_id": answer.trace_id,
                "query_type": answer.query_type.value,
                "filters": answer.filters,
                "warnings": (list(retrieval_trace.warnings) if retrieval_trace is not None else []),
                "timings_ms": (retrieval_trace.timings_ms if retrieval_trace is not None else {}),
            },
        )

    async def chat(self, case: EvaluationCase, retrieval: RetrievalResult) -> ChatResult:
        answer, token_count, cost = self._answers.pop(case.question_id)
        covered = frozenset(
            point
            for point in case.expected_answer_points
            if _contains_normalized(answer.answer, point)
        )
        claim_count, hallucinated_claims = _citation_claims(answer, retrieval)
        return ChatResult(
            answer=answer.answer,
            cited_chunk_ids=frozenset(citation.chunk_id for citation in answer.citations),
            cited_document_ids=frozenset(citation.document_id for citation in answer.citations),
            covered_answer_points=covered,
            refused=answer.refusal,
            claim_count=claim_count,
            hallucinated_claims=hallucinated_claims,
            latency_ms=0.0,
            token_count=token_count,
            cost=cost,
            metadata={
                "trace_id": answer.trace_id,
                "refusal_reasons": list(answer.refusal_reasons),
                "conflicts": list(answer.conflicts),
                "outdated": list(answer.outdated),
                "hallucination_method": "citation_quote_binding_v1",
            },
            # The evaluation metric deliberately does not consume the ChatService
            # gate result; it independently checks citation-bound claims below.
            grounding_validated=None,
        )


def _case(
    question: EvaluationQuestion,
    additional_filters: dict[str, Any] | None = None,
) -> EvaluationCase:
    expected_filters = {**question.expected_filters, **(additional_filters or {})}
    return EvaluationCase(
        question_id=question.question_id,
        question=question.question,
        expected_document_ids=frozenset(question.expected_document_ids),
        expected_chunk_ids=frozenset(question.expected_chunk_ids),
        expected_answer_points=frozenset(question.expected_answer_points),
        expected_filters=expected_filters,
        should_refuse=question.should_refuse,
        difficulty=question.difficulty,
        category=question.category,
        metadata={"query_type": question.query_type},
    )


def _question_model(question: EvaluationQuestionInput) -> EvaluationQuestion:
    return EvaluationQuestion(
        question_id=question.question_id,
        question=question.question,
        query_type=question.query_type,
        expected_document_ids=question.expected_document_ids,
        expected_chunk_ids=question.expected_chunk_ids,
        expected_answer_points=question.expected_answer_points,
        expected_filters=question.expected_filters,
        should_refuse=question.should_refuse,
        difficulty=question.difficulty,
        category=question.category,
        created_by=question.created_by,
        verified=question.verified,
    )


def _citation_claims(answer: ChatAnswer, retrieval: RetrievalResult) -> tuple[int, int]:
    if answer.refusal or not answer.citations:
        return 0, 0
    content_by_chunk = {
        item.chunk_id: str(item.metadata.get("content", "")) for item in retrieval.items
    }
    if answer.retrieval_trace is not None:
        content_by_chunk.update(
            {hit.chunk_id: hit.content for hit in answer.retrieval_trace.final_results}
        )
    citation_unbound = any(
        not _contains_normalized(content_by_chunk.get(citation.chunk_id, ""), citation.quote)
        for citation in answer.citations
    )
    cited_text = "\n".join(
        content_by_chunk.get(citation.chunk_id, "") for citation in answer.citations
    )
    claims = _evaluation_claims(answer.answer)
    if not claims:
        return 1, int(citation_unbound)
    hallucinated = sum(not _independent_claim_supported(claim, cited_text) for claim in claims)
    if citation_unbound:
        hallucinated = max(1, hallucinated)
    return len(claims), min(len(claims), hallucinated)


def _evaluation_claims(answer: str) -> tuple[str, ...]:
    return tuple(
        cleaned
        for part in re.split(r"[。！？!?；;\n]+", answer)
        if (cleaned := re.sub(r"https?://\S+|[（(]来源[:：].*?[)）]", " ", part).strip())
    )


def _independent_claim_supported(claim: str, evidence: str) -> bool:
    normalized_evidence = _normalize(evidence)
    exact_values = tuple(re.findall(r"(?:19|20)\d{2}|\d+(?:\.\d+)?(?:%|％|万元|亿元|元)", claim))
    if any(_normalize(value) not in normalized_evidence for value in exact_values):
        return False
    terms: set[str] = {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9._+-]{2,}", claim)}
    for segment in re.findall(r"[\u4e00-\u9fff]+", claim):
        terms.update(segment[index : index + 2] for index in range(max(0, len(segment) - 1)))
    terms -= {"根据", "来源", "文件", "通知", "政策", "回答", "证据"}
    if not terms:
        return True
    matched = sum(term in normalized_evidence for term in terms)
    return matched >= 2 and matched / len(terms) >= 0.2


def _contains_normalized(text: str, expected: str) -> bool:
    normalized_text = _normalize(text)
    normalized_expected = _normalize(expected)
    return bool(normalized_expected) and normalized_expected in normalized_text


def _normalize(value: str) -> str:
    return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]+", value.lower()))


def _token_count(payload: dict[str, Any]) -> int:
    for key in ("total_tokens", "tokens", "token_count"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value)
    prompt = payload.get("prompt_tokens")
    completion = payload.get("completion_tokens")
    return sum(
        value
        for value in (prompt, completion)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    )


def _artifact_paths(output_dir: Path) -> dict[str, str]:
    names = {
        "json": "evaluation.json",
        "csv": "questions.csv",
        "markdown": "report.md",
        "chart_data": "chart_data.json",
    }
    return {
        key: str((output_dir / filename).resolve())
        for key, filename in names.items()
        if (output_dir / filename).is_file()
    }


def _resolved_path(path: str) -> Path:
    return Path(path).resolve()


def _load_report(report_path: Path) -> Any:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"evaluation report is unavailable: {exc}") from exc
    return payload


def _utc_now() -> datetime:
    return datetime.now(UTC)
