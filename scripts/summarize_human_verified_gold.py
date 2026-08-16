from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # type: ignore[import-untyped]  # noqa: E402
from app.database.session import DatabaseManager  # type: ignore[import-untyped]  # noqa: E402
from app.models import QueryTrace  # type: ignore[import-untyped]  # noqa: E402


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize a human-verified evaluation report with persisted traces"
    )
    parser.add_argument("evaluation_json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quality-json", type=Path)
    parser.add_argument("--quality-ids", nargs="*", default=[])
    return parser.parse_args()


def _ndcg(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    ranked = list(dict.fromkeys(retrieved))[:k]
    dcg = sum(
        (1.0 if item in relevant else 0.0) / math.log2(rank + 1)
        for rank, item in enumerate(ranked, start=1)
    )
    ideal = sum(
        1.0 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1)
    )
    return dcg / ideal if ideal else 1.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _trace_id(case: dict[str, Any]) -> str | None:
    trace = case.get("retrieval_trace")
    return (
        str(trace["trace_id"])
        if isinstance(trace, dict) and trace.get("trace_id")
        else None
    )


def _case_metrics(case: dict[str, Any], trace: QueryTrace | None) -> dict[str, Any]:
    expected_refuse = bool(case.get("should_refuse"))
    actual_refuse = bool(case.get("refused"))
    evidence = dict(trace.evidence_decision_json or {}) if trace is not None else {}
    rerank = dict(trace.rerank_metadata_json or {}) if trace is not None else {}
    timings = dict(trace.stage_timings_json or {}) if trace is not None else {}
    return {
        "question_id": case.get("question_id"),
        "expected_refuse": expected_refuse,
        "actual_refuse": actual_refuse,
        "evaluation_failed": bool(case.get("error")),
        "cited_count": len(case.get("cited_chunk_ids") or []),
        "expected_chunk_count": len(case.get("expected_chunk_ids") or []),
        "answer_grounded": float(case.get("metrics", {}).get("answer_grounded", 0.0)),
        "document_citation_accuracy": float(
            case.get("metrics", {}).get("document_citation_accuracy", 0.0)
        ),
        "trace_id": _trace_id(case),
        "evidence_sufficient": evidence.get("sufficient"),
        "evidence_reason": evidence.get("reason"),
        "rerank_provider": rerank.get("provider"),
        "rerank_applied": rerank.get("applied"),
        "rerank_warning": next(
            (
                warning
                for warning in (case.get("retrieval_trace", {}).get("warnings") or [])
                if str(warning).startswith("rerank_failed_open:")
            ),
            None,
        ),
        "rerank_ms": timings.get("rerank")
        or timings.get("retrieval_rerank")
        or timings.get("retrieval-rerank"),
    }


def _quality_guard(
    cases: list[dict[str, Any]], trace_by_id: dict[str, QueryTrace]
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in cases:
        item = _case_metrics(case, trace_by_id.get(_trace_id(case) or ""))
        supported = not item["expected_refuse"]
        checks = {
            "expected_label": True,
            "remote_rerank_applied": item["rerank_provider"] == "remote"
            and item["rerank_applied"] is True
            and not item["rerank_warning"],
            "evidence_sufficient": item["evidence_sufficient"] is True
            if supported
            else True,
            "answer_state": (
                item["actual_refuse"] is False and item["cited_count"] > 0
                if supported
                else item["actual_refuse"] is True and item["cited_count"] == 0
            ),
            "citation_support": item["answer_grounded"] == 1.0 if supported else True,
            "no_unsupported_answer": (
                float(case.get("metrics", {}).get("unsupported_answer", 0.0)) == 0.0
            ),
        }
        results.append({**item, "checks": checks, "passed": all(checks.values())})
    return {
        "question_count": len(results),
        "supported_count": sum(not item["expected_refuse"] for item in results),
        "refusal_count": sum(item["expected_refuse"] for item in results),
        "passed_count": sum(item["passed"] for item in results),
        "status": "PASS-LIVE"
        if results and all(item["passed"] for item in results)
        else "FAIL-LIVE-QUALITY",
        "cases": results,
    }


async def _run(arguments: argparse.Namespace) -> dict[str, Any]:
    report = json.loads(arguments.evaluation_json.read_text(encoding="utf-8"))
    cases = list(report.get("questions") or [])
    trace_ids = [_trace_id(case) for case in cases]
    trace_ids = [trace_id for trace_id in trace_ids if trace_id]
    database = DatabaseManager(Settings())
    try:
        async with database.session_factory() as session:
            rows = (
                await session.execute(
                    select(QueryTrace).where(QueryTrace.trace_id.in_(trace_ids))
                )
            ).scalars()
            trace_by_id = {row.trace_id: row for row in rows}
    finally:
        await database.dispose()

    scored_cases = [case for case in cases if not case.get("error")]
    sample_ndcg5 = [
        _ndcg(
            list(case.get("retrieved_chunk_ids") or []),
            set(case.get("expected_chunk_ids") or []),
            5,
        )
        for case in scored_cases
    ]
    case_metrics = [
        _case_metrics(case, trace_by_id.get(_trace_id(case) or "")) for case in cases
    ]
    evidence_cases = [
        item for item in case_metrics if item["evidence_sufficient"] is not None
    ]
    evidence_accuracy = _mean(
        [
            float(item["evidence_sufficient"] == (not item["expected_refuse"]))
            for item in evidence_cases
        ]
    )
    rerank_remote = [
        item for item in case_metrics if item["rerank_provider"] == "remote"
    ]
    rerank_applied = [item for item in rerank_remote if item["rerank_applied"] is True]
    rerank_fail_open = [item for item in case_metrics if item["rerank_warning"]]
    aggregate = dict(report.get("aggregate") or {})
    assessed_case_metrics = [
        item for item in case_metrics if not item["evaluation_failed"]
    ]
    gold_answers = [
        item for item in assessed_case_metrics if not item["expected_refuse"]
    ]
    gold_refusals = [item for item in assessed_case_metrics if item["expected_refuse"]]
    predicted_refusals = [
        item for item in assessed_case_metrics if item["actual_refuse"]
    ]
    supported_answers = [item for item in gold_answers if not item["actual_refuse"]]
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "GOLD_EVALUATION_COMPLETE",
        "source_report": str(arguments.evaluation_json.resolve()),
        "run_name": report.get("run_name"),
        "evaluation_run_id": report.get("metadata", {}).get("evaluation_run_id"),
        "question_count": len(cases),
        "metrics": {
            "recall_at_5": aggregate.get("recall_at_5"),
            "recall_at_10": aggregate.get("recall_at_10"),
            "mrr": aggregate.get("mrr"),
            "ndcg_at_5": _mean(sample_ndcg5),
            "ndcg_at_10": aggregate.get("ndcg_at_10"),
            "citation_accuracy": aggregate.get("citation_accuracy"),
            "citation_precision": aggregate.get("citation_precision"),
            "citation_recall": aggregate.get("citation_recall"),
            "emitted_citation_precision": aggregate.get("emitted_citation_precision"),
            "emitted_citation_recall": aggregate.get("emitted_citation_recall"),
            "document_citation_precision": aggregate.get("document_citation_precision"),
            "document_citation_recall": aggregate.get("document_citation_recall"),
            "emitted_document_citation_precision": aggregate.get(
                "emitted_document_citation_precision"
            ),
            "emitted_document_citation_recall": aggregate.get(
                "emitted_document_citation_recall"
            ),
            "grounded_answer_rate": aggregate.get("answer_grounding_rate"),
            "refusal_accuracy": aggregate.get("refusal_accuracy"),
            "refusal_precision": _mean(
                [float(item["expected_refuse"]) for item in predicted_refusals]
            ),
            "refusal_recall": _mean(
                [float(item["actual_refuse"]) for item in gold_refusals]
            ),
            "supported_answer_recall": _mean(
                [float(not item["actual_refuse"]) for item in gold_answers]
            ),
            "unsupported_answer_rate": aggregate.get("unsupported_answer_rate"),
            "evidence_sufficiency_accuracy": evidence_accuracy,
        },
        "denominators": {
            "grounded_answer_questions": aggregate.get(
                "answer_grounding_assessed_questions", 0
            ),
            "citation_questions": aggregate.get("citation_assessed_questions", 0),
            "emitted_citation_questions": aggregate.get(
                "emitted_citation_assessed_questions", len(supported_answers)
            ),
            "unsupported_answer_questions": aggregate.get(
                "unsupported_answer_assessed_questions", 0
            ),
            "evidence_sufficiency_questions": len(evidence_cases),
            "evaluation_error_count": aggregate.get("evaluation_error_count", 0),
            "quality_assessed_questions": aggregate.get(
                "quality_assessed_questions", len(cases)
            ),
        },
        "remote_rerank": {
            "provider_trace_count": len(rerank_remote),
            "applied_count": len(rerank_applied),
            "fail_open_count": len(rerank_fail_open),
            "status": "PASS-LIVE"
            if rerank_remote and not rerank_fail_open
            else "PARTIAL-LIVE",
        },
        "quality_guard": None,
    }
    if arguments.quality_json:
        quality_report = json.loads(arguments.quality_json.read_text(encoding="utf-8"))
        selected = set(arguments.quality_ids)
        quality_cases = [
            case
            for case in quality_report.get("questions", [])
            if case.get("question_id") in selected
        ]
        quality_trace_ids = [_trace_id(case) for case in quality_cases]
        quality_trace_ids = [trace_id for trace_id in quality_trace_ids if trace_id]
        if quality_trace_ids:
            database = DatabaseManager(Settings())
            try:
                async with database.session_factory() as session:
                    rows = (
                        await session.execute(
                            select(QueryTrace).where(
                                QueryTrace.trace_id.in_(quality_trace_ids)
                            )
                        )
                    ).scalars()
                    quality_traces = {row.trace_id: row for row in rows}
            finally:
                await database.dispose()
        else:
            quality_traces = {}
        result["quality_guard"] = _quality_guard(quality_cases, quality_traces)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    result = asyncio.run(_run(_arguments()))
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
