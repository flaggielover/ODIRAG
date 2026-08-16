from __future__ import annotations

import csv
import json
import math
import uuid
from pathlib import Path

import pytest

from app.evaluation import (
    ChatResult,
    EvaluationCase,
    EvaluationRunner,
    EvaluationSample,
    RetrievalResult,
    RetrievedItem,
    evaluate_samples,
    write_evaluation_reports,
)
from app.services.evaluation import _independent_claim_supported


def test_extended_metrics_keep_the_original_sample_api() -> None:
    aggregate = evaluate_samples(
        [
            EvaluationSample(
                retrieved_ids=("c2", "c1"),
                relevant_ids=frozenset({"c1"}),
                expected_answer_points=frozenset({"p1", "p2"}),
                covered_answer_points=frozenset({"p1"}),
                expected_citation_ids=frozenset({"c1", "c3"}),
                cited_ids=frozenset({"c1", "unexpected"}),
                hallucinated_claims=1,
                claim_count=4,
                latency_ms=100,
                token_count=20,
                cost=0.1,
                retrieved_document_ids=("d2", "d1"),
                relevant_document_ids=frozenset({"d1"}),
                cited_document_ids=frozenset({"d1", "unexpected"}),
            ),
            EvaluationSample(
                retrieved_ids=("c9",),
                relevant_ids=frozenset({"c8"}),
                should_refuse=True,
                refused=True,
                latency_ms=300,
                token_count=40,
                cost=0.3,
                retrieved_document_ids=("d9",),
                relevant_document_ids=frozenset({"d8"}),
            ),
        ]
    )

    assert aggregate.document_hit_rate == 0.5
    assert aggregate.chunk_hit_rate == 0.5
    assert aggregate.recall_at_1 == 0.0
    assert aggregate.recall_at_5 == 0.5
    assert aggregate.mrr == 0.25
    assert aggregate.ndcg_at_10 == pytest.approx(0.5 / math.log2(3))
    assert aggregate.answer_point_coverage == 0.75
    assert aggregate.citation_accuracy == 0.5
    assert aggregate.citation_completeness == 0.5
    assert aggregate.citation_precision == 0.5
    assert aggregate.citation_recall == 0.5
    assert aggregate.emitted_citation_precision == 0.5
    assert aggregate.emitted_citation_recall == 0.5
    assert aggregate.document_citation_precision == 0.5
    assert aggregate.document_citation_recall == 1.0
    assert aggregate.emitted_document_citation_precision == 0.5
    assert aggregate.emitted_document_citation_recall == 1.0
    assert aggregate.refusal_accuracy == 1.0
    assert aggregate.refusal_precision == 1.0
    assert aggregate.refusal_recall == 1.0
    assert aggregate.supported_answer_recall == 1.0
    assert aggregate.hallucination_rate == 0.25
    assert aggregate.answer_grounding_rate == 0.0
    assert aggregate.unsupported_answer_rate == 0.0
    assert aggregate.hallucination_assessed_claims == 4
    assert aggregate.hallucination_assessed_questions == 1
    assert aggregate.p50_latency_ms == 100
    assert aggregate.p95_latency_ms == 300
    assert aggregate.average_tokens == 30
    assert aggregate.average_cost == pytest.approx(0.2)

    empty = evaluate_samples([])
    assert empty.question_count == 0
    assert empty.average_cost == 0.0


def test_safety_metrics_record_unsupported_answers_and_grounding() -> None:
    aggregate = evaluate_samples(
        [
            EvaluationSample(
                retrieved_ids=("c1",),
                relevant_ids=frozenset(),
                cited_ids=frozenset({"c1"}),
                should_refuse=True,
                refused=False,
                grounding_validated=False,
            ),
            EvaluationSample(
                retrieved_ids=("c2",),
                relevant_ids=frozenset({"c2"}),
                cited_ids=frozenset({"c2"}),
                refused=False,
                grounding_validated=True,
            ),
        ]
    )

    assert aggregate.unsupported_answer_rate == 1.0
    assert aggregate.answer_grounding_rate == 0.5
    assert aggregate.citation_assessed_questions == 2
    assert aggregate.answer_grounding_assessed_questions == 2
    assert aggregate.unsupported_answer_assessed_questions == 1


def test_citation_metrics_exclude_correct_refusals_from_denominator() -> None:
    samples = [
        EvaluationSample(
            retrieved_ids=(f"refusal-{index}",),
            relevant_ids=frozenset(),
            should_refuse=True,
            refused=True,
        )
        for index in range(9)
    ]
    samples.append(
        EvaluationSample(
            retrieved_ids=("wrong",),
            relevant_ids=frozenset({"expected"}),
            expected_citation_ids=frozenset({"expected"}),
            cited_ids=frozenset({"wrong"}),
            refused=False,
        )
    )

    aggregate = evaluate_samples(samples)

    assert aggregate.citation_precision == 0.0
    assert aggregate.citation_recall == 0.0


def test_citation_metrics_include_unsupported_answers_in_denominator() -> None:
    aggregate = evaluate_samples(
        [
            EvaluationSample(
                retrieved_ids=("correct",),
                relevant_ids=frozenset({"correct"}),
                expected_citation_ids=frozenset({"correct"}),
                cited_ids=frozenset({"correct"}),
            ),
            EvaluationSample(
                retrieved_ids=("wrong",),
                relevant_ids=frozenset(),
                cited_ids=frozenset({"wrong"}),
                should_refuse=True,
                refused=False,
            ),
        ]
    )

    assert aggregate.citation_precision == 0.5
    assert aggregate.citation_recall == 0.5
    assert aggregate.unsupported_answer_rate == 1.0


def test_independent_grounding_check_reads_answer_claims() -> None:
    evidence = "存量APP备案阶段为2023年9月至2024年3月。"

    assert _independent_claim_supported(
        "存量APP备案阶段为2023年9月至2024年3月",
        evidence,
    )
    assert not _independent_claim_supported("月球上发现了恐龙", evidence)
    assert not _independent_claim_supported("备案阶段为2025年1月", evidence)


@pytest.mark.asyncio
async def test_runner_uses_callbacks_and_reports_all_formats() -> None:
    seen_filters: list[dict[str, object]] = []

    async def retrieve(case: EvaluationCase) -> RetrievalResult:
        seen_filters.append(dict(case.expected_filters))
        if case.should_refuse:
            return RetrievalResult(latency_ms=5, token_count=1, cost=0.01)
        return RetrievalResult(
            items=(
                RetrievedItem("d2", "c2", 0.8),
                RetrievedItem("d1", "c1", 0.7),
            ),
            latency_ms=10,
            token_count=1,
            cost=0.01,
            trace={"mode": "hybrid"},
        )

    async def chat(case: EvaluationCase, _retrieval: RetrievalResult) -> ChatResult:
        if case.should_refuse:
            return ChatResult(
                answer="Insufficient evidence.",
                refused=True,
                latency_ms=5,
                token_count=3,
                cost=0.01,
            )
        return ChatResult(
            answer="Supported answer.",
            cited_chunk_ids=frozenset({"c1"}),
            covered_answer_points=frozenset({"p1"}),
            claim_count=2,
            hallucinated_claims=0,
            latency_ms=20,
            token_count=9,
            cost=0.09,
            metadata={"prompt_version": "v1"},
        )

    cases = [
        EvaluationCase(
            question_id="q1",
            question="What support is available?",
            expected_document_ids=frozenset({"d1"}),
            expected_chunk_ids=frozenset({"c1"}),
            expected_answer_points=frozenset({"p1", "p2"}),
            expected_filters={"region": "Sichuan"},
            difficulty="medium",
            category="policy",
        ),
        EvaluationCase(
            question_id="q2",
            question="Question outside the corpus",
            expected_filters={"region": "Sichuan"},
            should_refuse=True,
            difficulty="hard",
            category="refusal",
        ),
    ]
    result = await EvaluationRunner(retrieve, chat).run(
        cases,
        run_name="phase9-demo",
        metadata={"retrieval_version": "r1"},
    )

    assert seen_filters == [{"region": "Sichuan"}, {"region": "Sichuan"}]
    assert result.aggregate.question_count == 2
    assert result.aggregate.document_hit_rate == 1.0
    assert result.aggregate.chunk_hit_rate == 1.0
    assert result.aggregate.refusal_accuracy == 1.0
    assert result.questions[0].sample.latency_ms == 30
    assert result.questions[0].sample.token_count == 10
    assert result.questions[0].sample.cost == pytest.approx(0.1)

    output_dir = Path(".test-data") / "phase9" / str(uuid.uuid4())
    artifacts = write_evaluation_reports(result, output_dir)
    artifacts = write_evaluation_reports(result, output_dir)
    assert all(
        path.is_file()
        for path in (
            artifacts.json_path,
            artifacts.csv_path,
            artifacts.markdown_path,
            artifacts.chart_data_path,
        )
    )
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["aggregate"]["document_hit_rate"] == 1.0
    assert "claim_count=0" in payload["hallucination_measurement_scope"]
    with artifacts.csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["question_id"] for row in rows] == ["q1", "q2"]
    assert rows[0]["expected_citation_ids"] == "c1"
    assert rows[0]["covered_answer_points"] == "p1"
    assert "Evaluation Report: phase9-demo" in artifacts.markdown_path.read_text(encoding="utf-8")
    chart_data = json.loads(artifacts.chart_data_path.read_text(encoding="utf-8"))
    assert {item["key"] for item in chart_data["metrics"]} >= {
        "document_hit_rate",
        "recall_at_10",
        "citation_accuracy",
        "p95_latency_ms",
        "average_tokens",
    }
    assert not list(output_dir.glob("*.tmp"))


@pytest.mark.asyncio
async def test_runner_records_callback_failure_and_continues() -> None:
    async def broken_retrieval(_case: EvaluationCase) -> RetrievalResult:
        raise RuntimeError("retrieval unavailable")

    async def unexpected_chat(_case: EvaluationCase, _retrieval: RetrievalResult) -> ChatResult:
        raise AssertionError("chat must not run")

    result = await EvaluationRunner(broken_retrieval, unexpected_chat).run(
        [
            EvaluationCase(
                question_id="broken",
                question="Will this fail?",
                expected_document_ids=frozenset({"d1"}),
                expected_chunk_ids=frozenset({"c1"}),
            )
        ]
    )

    question = result.questions[0]
    assert question.error_stage == "retrieval"
    assert question.error == "RuntimeError: retrieval unavailable"
    assert question.metrics.document_hit == 0.0
    assert question.metrics.chunk_hit == 0.0
    assert result.aggregate.question_count == 1
    assert result.aggregate.evaluation_error_count == 1
    assert result.aggregate.quality_assessed_questions == 0
    assert result.aggregate.refusal_accuracy == 0.0
    assert result.aggregate.unsupported_answer_assessed_questions == 0
