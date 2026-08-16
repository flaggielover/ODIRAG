from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import make_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # type: ignore[import-untyped]  # noqa: E402
from app.database.session import DatabaseManager  # type: ignore[import-untyped]  # noqa: E402
from app.evaluation.failure_analysis import (  # noqa: E402
    build_failure_analysis,  # type: ignore[import-untyped]
)
from app.models import (  # type: ignore[import-untyped]  # noqa: E402
    Chunk,
    Document,
    QueryTrace,
    Source,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Human Gold failure matrix")
    parser.add_argument("evaluation_json", type=Path)
    parser.add_argument(
        "--gold-json",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "evaluation" / "phase_j_human_verified.json",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "evaluation" / "gold_failure_matrix.json",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "evaluation" / "gold_failure_matrix.csv",
    )
    parser.add_argument(
        "--database-host",
        help="Override only the configured database hostname, preserving credentials.",
    )
    parser.add_argument("--database-port", type=int)
    return parser.parse_args()


async def _run(arguments: argparse.Namespace) -> dict[str, Any]:
    evaluation = json.loads(arguments.evaluation_json.read_text(encoding="utf-8"))
    gold = json.loads(arguments.gold_json.read_text(encoding="utf-8"))
    trace_ids = [
        str((item.get("retrieval_trace") or {}).get("trace_id"))
        for item in evaluation.get("questions", [])
        if (item.get("retrieval_trace") or {}).get("trace_id")
    ]
    settings = Settings()
    if arguments.database_host or arguments.database_port:
        url = make_url(settings.database_url).set(
            host=arguments.database_host,
            port=arguments.database_port,
        )
        settings.database_url = url.render_as_string(hide_password=False)
    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            trace_rows = list(
                (
                    await session.execute(
                        select(QueryTrace).where(QueryTrace.trace_id.in_(trace_ids))
                    )
                ).scalars()
            )
            chunk_ids = {
                str(chunk_id)
                for item in evaluation.get("questions", [])
                for chunk_id in (
                    list(item.get("expected_chunk_ids") or [])
                    + list(item.get("cited_chunk_ids") or [])
                )
            }
            lineage_rows = (
                await session.execute(
                    select(Chunk, Document, Source)
                    .join(Document, Document.id == Chunk.document_id)
                    .join(Source, Source.id == Document.source_id)
                    .where(Chunk.chunk_id.in_(chunk_ids))
                )
            ).all()
    finally:
        await database.dispose()
    traces = {row.trace_id: _trace_payload(row) for row in trace_rows}
    lineage = {
        chunk.chunk_id: {
            "document_id": document.document_id,
            "document_title": document.title,
            "source_id": source.id,
            "source_key": source.source_key,
            "source_title": source.name,
            "source_url": document.source_url,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
        }
        for chunk, document, source in lineage_rows
    }
    analysis = build_failure_analysis(evaluation, gold, traces, lineage)
    if analysis["question_count"] != len(evaluation.get("questions", [])):
        raise ValueError("failure matrix did not preserve every evaluation question")
    _write_text(
        arguments.output_json,
        json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _write_text(arguments.output_csv, _cases_csv(analysis["cases"]))
    return analysis


def _trace_payload(row: QueryTrace) -> dict[str, Any]:
    return {
        "trace_id": row.trace_id,
        "fusion_results": row.fusion_results_json or [],
        "rerank_results": row.rerank_results_json or [],
        "final_context": row.final_context_json or [],
        "rerank_metadata": row.rerank_metadata_json or {},
        "evidence_decision": row.evidence_decision_json or {},
        "stage_timings": row.stage_timings_json or {},
    }


def _cases_csv(cases: list[dict[str, Any]]) -> str:
    output = StringIO(newline="")
    fieldnames = [
        "id",
        "category",
        "question",
        "should_refuse",
        "expected_answer",
        "expected_document_ids",
        "expected_chunk_ids",
        "retrieval_top5",
        "retrieval_top10",
        "reranked_chunks",
        "selected_evidence_chunks",
        "final_cited_chunk_ids",
        "refusal",
        "refusal_reason",
        "evidence_gate_result",
        "relation_validation_result",
        "citation_validation_result",
        "answer_present",
        "answer_correctness_status",
        "retrieval_hit",
        "expected_evidence_in_context",
        "metric_failures",
        "root_cause_category",
        "root_cause_detail",
        "trace_id",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for case in cases:
        writer.writerow({key: _csv_value(case.get(key)) for key in fieldnames})
    return output.getvalue()


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    analysis = asyncio.run(_run(_arguments()))
    print(
        json.dumps(
            {
                "question_count": analysis["question_count"],
                "root_cause_distribution": analysis["root_cause_distribution"],
                "refusal_confusion_matrix": analysis["refusal_confusion_matrix"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
