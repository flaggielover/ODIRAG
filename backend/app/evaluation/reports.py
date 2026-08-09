from __future__ import annotations

import csv
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from uuid import uuid4

from app.evaluation.runner import EvaluationQuestionResult, EvaluationRunResult

HALLUCINATION_SCOPE = (
    "Only claims explicitly assessed by the injected chat callback are measured. "
    "Questions with claim_count=0 are excluded from the hallucination-rate denominator."
)


@dataclass(frozen=True, slots=True)
class EvaluationReportArtifacts:
    json_path: Path
    csv_path: Path
    markdown_path: Path
    chart_data_path: Path


def write_evaluation_reports(
    result: EvaluationRunResult, output_dir: Path
) -> EvaluationReportArtifacts:
    """Write a complete report set, atomically replacing each artifact."""

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = EvaluationReportArtifacts(
        json_path=output_dir / "evaluation.json",
        csv_path=output_dir / "questions.csv",
        markdown_path=output_dir / "report.md",
        chart_data_path=output_dir / "chart_data.json",
    )
    payload = _run_payload(result)
    _atomic_write_text(
        artifacts.json_path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write_text(artifacts.csv_path, _questions_csv(result.questions))
    _atomic_write_text(artifacts.markdown_path, _markdown(result))
    _atomic_write_text(
        artifacts.chart_data_path,
        json.dumps(_chart_data(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return artifacts


def _run_payload(result: EvaluationRunResult) -> dict[str, object]:
    return {
        "run_name": result.run_name,
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "metadata": _json_safe(result.metadata),
        "aggregate": asdict(result.aggregate),
        "hallucination_measurement_scope": HALLUCINATION_SCOPE,
        "questions": [_question_payload(question) for question in result.questions],
    }


def _question_payload(result: EvaluationQuestionResult) -> dict[str, object]:
    case = result.case
    retrieval = result.retrieval
    chat = result.chat
    return {
        "question_id": case.question_id,
        "question": case.question,
        "difficulty": case.difficulty,
        "category": case.category,
        "expected_document_ids": sorted(case.expected_document_ids),
        "expected_chunk_ids": sorted(case.expected_chunk_ids),
        "expected_answer_points": sorted(case.expected_answer_points),
        "expected_citation_ids": sorted(result.sample.expected_citation_ids),
        "expected_filters": _json_safe(case.expected_filters),
        "should_refuse": case.should_refuse,
        "retrieved_document_ids": list(result.sample.retrieved_document_ids),
        "retrieved_chunk_ids": list(result.sample.retrieved_ids),
        "covered_answer_points": sorted(result.sample.covered_answer_points),
        "cited_chunk_ids": sorted(result.sample.cited_ids),
        "cited_document_ids": sorted(result.sample.cited_document_ids),
        "refused": result.sample.refused,
        "answer": chat.answer if chat is not None else None,
        "metrics": asdict(result.metrics),
        "latency_ms": result.sample.latency_ms,
        "token_count": result.sample.token_count,
        "cost": result.sample.cost,
        "claim_count": result.sample.claim_count,
        "hallucinated_claims": result.sample.hallucinated_claims,
        "retrieval_trace": (_json_safe(retrieval.trace) if retrieval is not None else None),
        "chat_metadata": _json_safe(chat.metadata) if chat is not None else None,
        "error_stage": result.error_stage,
        "error": result.error,
    }


def _questions_csv(results: Sequence[EvaluationQuestionResult]) -> str:
    output = StringIO(newline="")
    fieldnames = [
        "question_id",
        "question",
        "difficulty",
        "category",
        "expected_document_ids",
        "retrieved_document_ids",
        "expected_chunk_ids",
        "retrieved_chunk_ids",
        "expected_answer_points",
        "covered_answer_points",
        "expected_citation_ids",
        "cited_chunk_ids",
        "document_hit",
        "chunk_hit",
        "recall_at_1",
        "recall_at_5",
        "recall_at_10",
        "reciprocal_rank",
        "ndcg_at_10",
        "answer_point_coverage",
        "citation_accuracy",
        "citation_completeness",
        "should_refuse",
        "refused",
        "refusal_correct",
        "hallucinated_claims",
        "claim_count",
        "hallucination_rate",
        "answer_grounded",
        "unsupported_answer",
        "latency_ms",
        "token_count",
        "cost",
        "answer",
        "expected_filters",
        "error_stage",
        "error",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for result in results:
        metrics = result.metrics
        writer.writerow(
            {
                "question_id": result.case.question_id,
                "question": result.case.question,
                "difficulty": result.case.difficulty or "",
                "category": result.case.category or "",
                "expected_document_ids": "|".join(sorted(result.case.expected_document_ids)),
                "retrieved_document_ids": "|".join(result.sample.retrieved_document_ids),
                "expected_chunk_ids": "|".join(sorted(result.case.expected_chunk_ids)),
                "retrieved_chunk_ids": "|".join(result.sample.retrieved_ids),
                "expected_answer_points": "|".join(sorted(result.sample.expected_answer_points)),
                "covered_answer_points": "|".join(sorted(result.sample.covered_answer_points)),
                "expected_citation_ids": "|".join(sorted(result.sample.expected_citation_ids)),
                "cited_chunk_ids": "|".join(sorted(result.sample.cited_ids)),
                "document_hit": metrics.document_hit,
                "chunk_hit": metrics.chunk_hit,
                "recall_at_1": metrics.recall_at_1,
                "recall_at_5": metrics.recall_at_5,
                "recall_at_10": metrics.recall_at_10,
                "reciprocal_rank": metrics.reciprocal_rank,
                "ndcg_at_10": metrics.ndcg_at_10,
                "answer_point_coverage": metrics.answer_point_coverage,
                "citation_accuracy": metrics.citation_accuracy,
                "citation_completeness": metrics.citation_completeness,
                "should_refuse": result.case.should_refuse,
                "refused": result.sample.refused,
                "refusal_correct": metrics.refusal_correct,
                "hallucinated_claims": result.sample.hallucinated_claims,
                "claim_count": result.sample.claim_count,
                "hallucination_rate": metrics.hallucination_rate,
                "answer_grounded": metrics.answer_grounded,
                "unsupported_answer": metrics.unsupported_answer,
                "latency_ms": result.sample.latency_ms,
                "token_count": result.sample.token_count,
                "cost": result.sample.cost,
                "answer": result.chat.answer if result.chat is not None else "",
                "expected_filters": json.dumps(
                    _json_safe(result.case.expected_filters),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "error_stage": result.error_stage or "",
                "error": result.error or "",
            }
        )
    return output.getvalue()


def _markdown(result: EvaluationRunResult) -> str:
    aggregate = asdict(result.aggregate)
    lines = [
        f"# Evaluation Report: {result.run_name}",
        "",
        f"Questions: {result.aggregate.question_count}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {_format_metric(value)} |" for key, value in aggregate.items())
    lines.extend(
        [
            "",
            "## Hallucination Measurement Scope",
            "",
            HALLUCINATION_SCOPE,
            "",
            "## Failed Questions",
            "",
        ]
    )
    failures = [question for question in result.questions if question.error]
    if failures:
        lines.extend(["| Question ID | Stage | Error |", "| --- | --- | --- |"])
        lines.extend(
            f"| {item.case.question_id} | {item.error_stage or ''} | {_markdown_cell(item.error)} |"
            for item in failures
        )
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def _chart_data(result: EvaluationRunResult) -> dict[str, object]:
    aggregate = result.aggregate
    metric_specs = (
        ("document_hit_rate", "ratio"),
        ("chunk_hit_rate", "ratio"),
        ("recall_at_1", "ratio"),
        ("recall_at_5", "ratio"),
        ("recall_at_10", "ratio"),
        ("mrr", "ratio"),
        ("ndcg_at_10", "ratio"),
        ("answer_point_coverage", "ratio"),
        ("citation_accuracy", "ratio"),
        ("citation_completeness", "ratio"),
        ("refusal_accuracy", "ratio"),
        ("hallucination_rate", "ratio"),
        ("citation_precision", "ratio"),
        ("citation_recall", "ratio"),
        ("answer_grounding_rate", "ratio"),
        ("unsupported_answer_rate", "ratio"),
        ("p50_latency_ms", "ms"),
        ("p95_latency_ms", "ms"),
        ("average_tokens", "tokens"),
        ("average_cost", "cost"),
        ("hallucination_assessed_claims", "count"),
        ("hallucination_assessed_questions", "count"),
    )
    return {
        "run_name": result.run_name,
        "metrics": [
            {"key": key, "value": getattr(aggregate, key), "unit": unit}
            for key, unit in metric_specs
        ],
        "latency_ms": [
            {"question_id": item.case.question_id, "value": item.sample.latency_ms}
            for item in result.questions
        ],
        "tokens": [
            {"question_id": item.case.question_id, "value": item.sample.token_count}
            for item in result.questions
        ],
        "cost": [
            {"question_id": item.case.question_id, "value": item.sample.cost}
            for item in result.questions
        ],
    }


def _atomic_write_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return [_json_safe(item) for item in sorted(value, key=str)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return str(value)


def _format_metric(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _markdown_cell(value: str | None) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ")
