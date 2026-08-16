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
    evaluation_failed: bool = False


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
    document_citation_accuracy: float
    document_citation_completeness: float
    refusal_correct: float
    hallucination_rate: float
    answer_grounded: float
    unsupported_answer: float
    evaluation_success: float


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
    emitted_citation_precision: float
    emitted_citation_recall: float
    document_citation_precision: float
    document_citation_recall: float
    emitted_document_citation_precision: float
    emitted_document_citation_recall: float
    answer_grounding_rate: float
    unsupported_answer_rate: float
    refusal_precision: float
    refusal_recall: float
    supported_answer_recall: float
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
    emitted_citation_assessed_questions: int = 0
    evaluation_error_count: int = 0
    quality_assessed_questions: int = 0


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
        document_citation_accuracy=_set_precision(
            sample.cited_document_ids, sample.relevant_document_ids
        ),
        document_citation_completeness=_citation_recall(
            sample.cited_document_ids, sample.relevant_document_ids
        ),
        refusal_correct=float(
            not sample.evaluation_failed and sample.refused == sample.should_refuse
        ),
        hallucination_rate=(
            sample.hallucinated_claims / sample.claim_count if sample.claim_count > 0 else 0.0
        ),
        answer_grounded=_answer_grounded(sample, cited),
        unsupported_answer=float(
            not sample.evaluation_failed and sample.should_refuse and not sample.refused
        ),
        evaluation_success=float(not sample.evaluation_failed),
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
            emitted_citation_precision=0.0,
            emitted_citation_recall=0.0,
            document_citation_precision=0.0,
            document_citation_recall=0.0,
            emitted_document_citation_precision=0.0,
            emitted_document_citation_recall=0.0,
            answer_grounding_rate=0.0,
            unsupported_answer_rate=0.0,
            refusal_precision=0.0,
            refusal_recall=0.0,
            supported_answer_recall=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
            average_tokens=0.0,
            average_cost=0.0,
        )
    measured = [evaluate_sample(sample) for sample in samples]
    scored_pairs = [
        (sample, item)
        for sample, item in zip(samples, measured, strict=True)
        if not sample.evaluation_failed
    ]
    scored = [item for _sample, item in scored_pairs]
    latencies = sorted(sample.latency_ms for sample in samples)
    assessed_claims = sum(sample.claim_count for sample in samples if sample.claim_count > 0)
    hallucinated_claims = sum(
        sample.hallucinated_claims for sample in samples if sample.claim_count > 0
    )
    answered_metrics = [item for sample, item in scored_pairs if not sample.refused]
    refusal_cases = [item for sample, item in scored_pairs if sample.should_refuse]
    citation_samples = [
        item for sample, item in scored_pairs if not (sample.should_refuse and sample.refused)
    ]
    citation_precision = (
        mean(item.citation_accuracy for item in citation_samples) if citation_samples else 0.0
    )
    citation_recall = (
        mean(item.citation_completeness for item in citation_samples) if citation_samples else 0.0
    )
    emitted_citation_precision = (
        mean(item.citation_accuracy for item in answered_metrics) if answered_metrics else 0.0
    )
    emitted_citation_recall = (
        mean(item.citation_completeness for item in answered_metrics) if answered_metrics else 0.0
    )
    document_citation_precision = (
        mean(item.document_citation_accuracy for item in citation_samples)
        if citation_samples
        else 0.0
    )
    document_citation_recall = (
        mean(item.document_citation_completeness for item in citation_samples)
        if citation_samples
        else 0.0
    )
    emitted_document_citation_precision = (
        mean(item.document_citation_accuracy for item in answered_metrics)
        if answered_metrics
        else 0.0
    )
    emitted_document_citation_recall = (
        mean(item.document_citation_completeness for item in answered_metrics)
        if answered_metrics
        else 0.0
    )
    scored_samples = [sample for sample, _item in scored_pairs]
    predicted_refusals = sum(sample.refused for sample in scored_samples)
    expected_refusals = sum(sample.should_refuse for sample in scored_samples)
    correct_refusals = sum(sample.refused and sample.should_refuse for sample in scored_samples)
    supported_questions = sum(not sample.should_refuse for sample in scored_samples)
    supported_answers = sum(
        not sample.should_refuse and not sample.refused for sample in scored_samples
    )
    return EvaluationAggregate(
        question_count=len(samples),
        recall_at_1=_mean_metric(scored, "recall_at_1"),
        recall_at_5=_mean_metric(scored, "recall_at_5"),
        recall_at_10=_mean_metric(scored, "recall_at_10"),
        mrr=_mean_metric(scored, "reciprocal_rank"),
        ndcg_at_10=_mean_metric(scored, "ndcg_at_10"),
        answer_point_coverage=_mean_metric(scored, "answer_point_coverage"),
        citation_accuracy=citation_precision,
        citation_completeness=citation_recall,
        refusal_accuracy=_mean_metric(scored, "refusal_correct"),
        hallucination_rate=(hallucinated_claims / assessed_claims if assessed_claims else 0.0),
        citation_precision=citation_precision,
        citation_recall=citation_recall,
        emitted_citation_precision=emitted_citation_precision,
        emitted_citation_recall=emitted_citation_recall,
        document_citation_precision=document_citation_precision,
        document_citation_recall=document_citation_recall,
        emitted_document_citation_precision=emitted_document_citation_precision,
        emitted_document_citation_recall=emitted_document_citation_recall,
        answer_grounding_rate=(
            mean(item.answer_grounded for item in answered_metrics) if answered_metrics else 0.0
        ),
        unsupported_answer_rate=(
            mean(item.unsupported_answer for item in refusal_cases) if refusal_cases else 0.0
        ),
        refusal_precision=(correct_refusals / predicted_refusals if predicted_refusals else 0.0),
        refusal_recall=(correct_refusals / expected_refusals if expected_refusals else 0.0),
        supported_answer_recall=(
            supported_answers / supported_questions if supported_questions else 0.0
        ),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        average_tokens=mean(sample.token_count for sample in samples),
        average_cost=mean(sample.cost for sample in samples),
        document_hit_rate=_mean_metric(scored, "document_hit"),
        chunk_hit_rate=_mean_metric(scored, "chunk_hit"),
        hallucination_assessed_claims=assessed_claims,
        hallucination_assessed_questions=sum(sample.claim_count > 0 for sample in samples),
        citation_assessed_questions=len(citation_samples),
        answer_grounding_assessed_questions=len(answered_metrics),
        unsupported_answer_assessed_questions=len(refusal_cases),
        emitted_citation_assessed_questions=len(answered_metrics),
        evaluation_error_count=sum(sample.evaluation_failed for sample in samples),
        quality_assessed_questions=len(scored),
    )


def _mean_metric(items: list[EvaluationSampleMetrics], field: str) -> float:
    return mean(float(getattr(item, field)) for item in items) if items else 0.0


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
