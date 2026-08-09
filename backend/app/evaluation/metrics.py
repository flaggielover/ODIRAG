from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True, slots=True)
class EvaluationSample:
    """One measured question.

    ``retrieved_ids`` and ``relevant_ids`` remain the chunk-level fields used by the
    original API. Document-level identities are appended so existing positional callers
    continue to work unchanged.
    """

    retrieved_ids: tuple[str, ...]
    relevant_ids: frozenset[str]
    expected_answer_points: frozenset[str] = frozenset()
    covered_answer_points: frozenset[str] = frozenset()
    expected_citation_ids: frozenset[str] = frozenset()
    cited_ids: frozenset[str] = frozenset()
    should_refuse: bool = False
    refused: bool = False
    hallucinated_claims: int = 0
    claim_count: int = 0
    latency_ms: float = 0.0
    token_count: int = 0
    cost: float = 0.0
    retrieved_document_ids: tuple[str, ...] = ()
    relevant_document_ids: frozenset[str] = frozenset()
    cited_document_ids: frozenset[str] = frozenset()
    grounding_validated: bool | None = None


@dataclass(frozen=True, slots=True)
class EvaluationSampleMetrics:
    document_hit: float
    chunk_hit: float
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    reciprocal_rank: float
    ndcg_at_10: float
    answer_point_coverage: float
    citation_accuracy: float
    citation_completeness: float
    refusal_correct: float
    hallucination_rate: float
    answer_grounded: float
    unsupported_answer: float


@dataclass(frozen=True, slots=True)
class EvaluationAggregate:
    question_count: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    answer_point_coverage: float
    citation_accuracy: float
    citation_completeness: float
    refusal_accuracy: float
    hallucination_rate: float
    citation_precision: float
    citation_recall: float
    answer_grounding_rate: float
    unsupported_answer_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    average_tokens: float
    average_cost: float
    document_hit_rate: float = 0.0
    chunk_hit_rate: float = 0.0
    hallucination_assessed_claims: int = 0
    hallucination_assessed_questions: int = 0
    citation_assessed_questions: int = 0
    answer_grounding_assessed_questions: int = 0
    unsupported_answer_assessed_questions: int = 0


def evaluate_sample(sample: EvaluationSample) -> EvaluationSampleMetrics:
    """Calculate the per-question values used by aggregate and report output."""

    cited, expected_citations = _citation_sets(sample)
    return EvaluationSampleMetrics(
        document_hit=_hit(sample.retrieved_document_ids, sample.relevant_document_ids),
        chunk_hit=_hit(sample.retrieved_ids, sample.relevant_ids),
        recall_at_1=_recall(sample, 1),
        recall_at_5=_recall(sample, 5),
        recall_at_10=_recall(sample, 10),
        reciprocal_rank=_reciprocal_rank(sample),
        ndcg_at_10=_ndcg(sample, 10),
        answer_point_coverage=_set_recall(
            sample.covered_answer_points, sample.expected_answer_points
        ),
        citation_accuracy=_set_precision(cited, expected_citations),
        citation_completeness=_citation_recall(cited, expected_citations),
        refusal_correct=float(sample.refused == sample.should_refuse),
        hallucination_rate=(
            sample.hallucinated_claims / sample.claim_count if sample.claim_count > 0 else 0.0
        ),
        answer_grounded=_answer_grounded(sample, cited),
        unsupported_answer=float(sample.should_refuse and not sample.refused),
    )


def evaluate_samples(samples: list[EvaluationSample]) -> EvaluationAggregate:
    if not samples:
        return EvaluationAggregate(
            question_count=0,
            recall_at_1=0.0,
            recall_at_5=0.0,
            recall_at_10=0.0,
            mrr=0.0,
            ndcg_at_10=0.0,
            answer_point_coverage=0.0,
            citation_accuracy=0.0,
            citation_completeness=0.0,
            refusal_accuracy=0.0,
            hallucination_rate=0.0,
            citation_precision=0.0,
            citation_recall=0.0,
            answer_grounding_rate=0.0,
            unsupported_answer_rate=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
            average_tokens=0.0,
            average_cost=0.0,
        )
    measured = [evaluate_sample(sample) for sample in samples]
    latencies = sorted(sample.latency_ms for sample in samples)
    assessed_claims = sum(sample.claim_count for sample in samples if sample.claim_count > 0)
    hallucinated_claims = sum(
        sample.hallucinated_claims for sample in samples if sample.claim_count > 0
    )
    answered_metrics = [
        item for sample, item in zip(samples, measured, strict=True) if not sample.refused
    ]
    refusal_cases = [
        item for sample, item in zip(samples, measured, strict=True) if sample.should_refuse
    ]
    citation_samples = [
        item
        for sample, item in zip(samples, measured, strict=True)
        if not (sample.should_refuse and sample.refused)
    ]
    citation_precision = (
        mean(item.citation_accuracy for item in citation_samples) if citation_samples else 0.0
    )
    citation_recall = (
        mean(item.citation_completeness for item in citation_samples) if citation_samples else 0.0
    )
    return EvaluationAggregate(
        question_count=len(samples),
        recall_at_1=mean(item.recall_at_1 for item in measured),
        recall_at_5=mean(item.recall_at_5 for item in measured),
        recall_at_10=mean(item.recall_at_10 for item in measured),
        mrr=mean(item.reciprocal_rank for item in measured),
        ndcg_at_10=mean(item.ndcg_at_10 for item in measured),
        answer_point_coverage=mean(item.answer_point_coverage for item in measured),
        citation_accuracy=citation_precision,
        citation_completeness=citation_recall,
        refusal_accuracy=mean(item.refusal_correct for item in measured),
        hallucination_rate=(hallucinated_claims / assessed_claims if assessed_claims else 0.0),
        citation_precision=citation_precision,
        citation_recall=citation_recall,
        answer_grounding_rate=(
            mean(item.answer_grounded for item in answered_metrics) if answered_metrics else 0.0
        ),
        unsupported_answer_rate=(
            mean(item.unsupported_answer for item in refusal_cases) if refusal_cases else 0.0
        ),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        average_tokens=mean(sample.token_count for sample in samples),
        average_cost=mean(sample.cost for sample in samples),
        document_hit_rate=mean(item.document_hit for item in measured),
        chunk_hit_rate=mean(item.chunk_hit for item in measured),
        hallucination_assessed_claims=assessed_claims,
        hallucination_assessed_questions=sum(sample.claim_count > 0 for sample in samples),
        citation_assessed_questions=len(citation_samples),
        answer_grounding_assessed_questions=len(answered_metrics),
        unsupported_answer_assessed_questions=len(refusal_cases),
    )


def _hit(retrieved: tuple[str, ...], relevant: frozenset[str]) -> float:
    if not relevant:
        return 1.0
    return float(any(item_id in relevant for item_id in retrieved))


def _recall(sample: EvaluationSample, k: int) -> float:
    retrieved, relevant = _ranking_sets(sample)
    if not relevant:
        return 1.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def _reciprocal_rank(sample: EvaluationSample) -> float:
    retrieved, relevant = _ranking_sets(sample)
    for rank, item_id in enumerate(_unique(retrieved), start=1):
        if item_id in relevant:
            return 1.0 / rank
    return 1.0 if not relevant else 0.0


def _ndcg(sample: EvaluationSample, k: int) -> float:
    retrieved, relevant = _ranking_sets(sample)
    ranked = _unique(retrieved)[:k]
    gains = [1.0 if item_id in relevant else 0.0 for item_id in ranked]
    dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal_length = min(k, len(relevant))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_length + 1))
    return dcg / idcg if idcg else 1.0


def _set_precision(actual: frozenset[str], expected: frozenset[str]) -> float:
    if not actual:
        return 0.0
    return len(actual & expected) / len(actual)


def _set_recall(actual: frozenset[str], expected: frozenset[str]) -> float:
    if not expected:
        return 1.0
    return len(actual & expected) / len(expected)


def _citation_recall(actual: frozenset[str], expected: frozenset[str]) -> float:
    if not expected:
        return 0.0
    return len(actual & expected) / len(expected)


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, math.ceil(quantile * len(values)) - 1)
    return values[index]


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _ranking_sets(sample: EvaluationSample) -> tuple[tuple[str, ...], frozenset[str]]:
    if sample.relevant_ids:
        return sample.retrieved_ids, sample.relevant_ids
    return sample.retrieved_document_ids, sample.relevant_document_ids


def _citation_sets(sample: EvaluationSample) -> tuple[frozenset[str], frozenset[str]]:
    if sample.expected_citation_ids or sample.should_refuse:
        return sample.cited_ids, sample.expected_citation_ids
    if sample.relevant_document_ids:
        return sample.cited_document_ids, sample.relevant_document_ids
    return sample.cited_ids, sample.expected_citation_ids


def _answer_grounded(sample: EvaluationSample, cited: frozenset[str]) -> float:
    if sample.refused:
        return 0.0
    if sample.grounding_validated is not None:
        return float(sample.grounding_validated)
    if not cited:
        return 0.0
    if sample.claim_count > 0:
        return float(sample.hallucinated_claims == 0)
    return 1.0
