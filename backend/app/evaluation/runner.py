from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.evaluation.metrics import (
    EvaluationAggregate,
    EvaluationSample,
    EvaluationSampleMetrics,
    evaluate_sample,
    evaluate_samples,
)


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    question_id: str
    question: str
    expected_document_ids: frozenset[str] = frozenset()
    expected_chunk_ids: frozenset[str] = frozenset()
    expected_answer_points: frozenset[str] = frozenset()
    expected_citation_ids: frozenset[str] = frozenset()
    expected_filters: Mapping[str, object] = field(default_factory=dict)
    should_refuse: bool = False
    difficulty: str | None = None
    category: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievedItem:
    document_id: str
    chunk_id: str
    score: float = 0.0
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    items: tuple[RetrievedItem, ...] = ()
    latency_ms: float | None = None
    token_count: int = 0
    cost: float = 0.0
    trace: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChatResult:
    answer: str
    cited_chunk_ids: frozenset[str] = frozenset()
    cited_document_ids: frozenset[str] = frozenset()
    covered_answer_points: frozenset[str] = frozenset()
    refused: bool = False
    claim_count: int = 0
    hallucinated_claims: int = 0
    latency_ms: float | None = None
    token_count: int = 0
    cost: float = 0.0
    metadata: Mapping[str, object] = field(default_factory=dict)
    grounding_validated: bool | None = None


class RetrievalCallback(Protocol):
    async def __call__(self, case: EvaluationCase) -> RetrievalResult: ...


class ChatCallback(Protocol):
    async def __call__(self, case: EvaluationCase, retrieval: RetrievalResult) -> ChatResult: ...


@dataclass(frozen=True, slots=True)
class EvaluationQuestionResult:
    case: EvaluationCase
    sample: EvaluationSample
    metrics: EvaluationSampleMetrics
    retrieval: RetrievalResult | None
    chat: ChatResult | None
    error_stage: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationRunResult:
    run_name: str
    started_at: datetime
    finished_at: datetime
    aggregate: EvaluationAggregate
    questions: tuple[EvaluationQuestionResult, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)


class EvaluationRunner:
    """Execute verified cases through injected retrieval and chat implementations."""

    def __init__(
        self,
        retrieval_callback: RetrievalCallback,
        chat_callback: ChatCallback,
        *,
        fail_fast: bool = False,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.retrieval_callback = retrieval_callback
        self.chat_callback = chat_callback
        self.fail_fast = fail_fast
        self.clock = clock

    async def run(
        self,
        cases: Sequence[EvaluationCase],
        *,
        run_name: str = "evaluation",
        metadata: Mapping[str, object] | None = None,
    ) -> EvaluationRunResult:
        started_at = datetime.now(UTC)
        results = []
        for case in cases:
            results.append(await self._run_case(case))
        finished_at = datetime.now(UTC)
        samples = [result.sample for result in results]
        return EvaluationRunResult(
            run_name=run_name,
            started_at=started_at,
            finished_at=finished_at,
            aggregate=evaluate_samples(samples),
            questions=tuple(results),
            metadata=dict(metadata or {}),
        )

    async def _run_case(self, case: EvaluationCase) -> EvaluationQuestionResult:
        retrieval: RetrievalResult | None = None
        chat: ChatResult | None = None
        retrieval_latency = 0.0
        chat_latency = 0.0
        error_stage: str | None = None
        error: str | None = None
        try:
            started = self.clock()
            retrieval = await self.retrieval_callback(case)
            retrieval_latency = self._latency(retrieval.latency_ms, started)
            started = self.clock()
            chat = await self.chat_callback(case, retrieval)
            chat_latency = self._latency(chat.latency_ms, started)
        except Exception as exc:
            if self.fail_fast:
                raise
            if retrieval is None:
                retrieval_latency = self._latency(None, started)
                error_stage = "retrieval"
            else:
                chat_latency = self._latency(None, started)
                error_stage = "chat"
            error = f"{exc.__class__.__name__}: {exc}"
        sample = self._sample(
            case,
            retrieval,
            chat,
            latency_ms=retrieval_latency + chat_latency,
            evaluation_failed=error is not None,
        )
        return EvaluationQuestionResult(
            case=case,
            sample=sample,
            metrics=evaluate_sample(sample),
            retrieval=retrieval,
            chat=chat,
            error_stage=error_stage,
            error=error,
        )

    def _latency(self, explicit_ms: float | None, started: float) -> float:
        if explicit_ms is not None:
            return max(0.0, explicit_ms)
        return max(0.0, (self.clock() - started) * 1000)

    @staticmethod
    def _sample(
        case: EvaluationCase,
        retrieval: RetrievalResult | None,
        chat: ChatResult | None,
        *,
        latency_ms: float,
        evaluation_failed: bool = False,
    ) -> EvaluationSample:
        items = retrieval.items if retrieval is not None else ()
        retrieved_chunks = tuple(item.chunk_id for item in items if item.chunk_id)
        retrieved_documents = tuple(
            dict.fromkeys(item.document_id for item in items if item.document_id)
        )
        expected_citations = case.expected_citation_ids or case.expected_chunk_ids
        return EvaluationSample(
            retrieved_ids=retrieved_chunks,
            relevant_ids=case.expected_chunk_ids,
            expected_answer_points=case.expected_answer_points,
            covered_answer_points=(chat.covered_answer_points if chat is not None else frozenset()),
            expected_citation_ids=expected_citations,
            cited_ids=chat.cited_chunk_ids if chat is not None else frozenset(),
            should_refuse=case.should_refuse,
            refused=chat.refused if chat is not None else False,
            hallucinated_claims=chat.hallucinated_claims if chat is not None else 0,
            claim_count=chat.claim_count if chat is not None else 0,
            latency_ms=latency_ms,
            token_count=(retrieval.token_count if retrieval is not None else 0)
            + (chat.token_count if chat is not None else 0),
            cost=(retrieval.cost if retrieval is not None else 0.0)
            + (chat.cost if chat is not None else 0.0),
            retrieved_document_ids=retrieved_documents,
            relevant_document_ids=case.expected_document_ids,
            cited_document_ids=(chat.cited_document_ids if chat is not None else frozenset()),
            grounding_validated=(chat.grounding_validated if chat is not None else None),
            evaluation_failed=evaluation_failed,
        )
