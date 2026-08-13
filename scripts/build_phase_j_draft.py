from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a real-corpus Phase J draft evaluation set")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "evaluation" / "phase_j_draft.json",
    )
    parser.add_argument(
        "--result-output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "evaluation" / "evaluation_results.json",
    )
    return parser.parse_args()


async def _run(limit: int, output: Path, result_output: Path) -> None:
    import anyio

    from app.config import Settings
    from app.database.session import DatabaseManager
    from app.evaluation.draft_dataset import (
        build_draft_evaluation_dataset,
        validate_draft_dataset,
    )

    database = DatabaseManager(Settings())
    try:
        async with database.session_factory() as session:
            dataset = await build_draft_evaluation_dataset(session, limit=limit)
            validate_draft_dataset(dataset, expected_size=limit)
    finally:
        await database.dispose()
    await anyio.Path(output.parent).mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    await anyio.Path(temporary).write_text(
        json.dumps(dataset.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    await anyio.Path(temporary).replace(output)
    result_payload = {
        "status": "NOT_RUN",
        "dataset_status": dataset.status,
        "blocker": "BLOCKED-HUMAN-EVAL-REVIEW",
        "question_count": dataset.question_count,
        "human_verified_count": dataset.human_verified_count,
        "retrieval_modes": ["bm25", "vector", "hybrid", "hybrid_rerank"],
        "metrics": {
            "recall_at_5": None,
            "recall_at_10": None,
            "mrr": None,
            "ndcg_at_5": None,
            "ndcg_at_10": None,
            "citation_accuracy": None,
            "citation_precision": None,
            "citation_recall": None,
            "grounded_answer_rate": None,
            "refusal_accuracy": None,
            "unsupported_answer_rate": None,
        },
        "notes": [
            "Candidate questions are derived from real persisted official documents and chunks.",
            "Metrics remain null until a human verifies questions, expected answers, and evidence.",
            "Remote rerank is independently blocked by missing external credentials.",
        ],
    }
    await anyio.Path(result_output.parent).mkdir(parents=True, exist_ok=True)
    result_temporary = result_output.with_suffix(result_output.suffix + ".tmp")
    await anyio.Path(result_temporary).write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    await anyio.Path(result_temporary).replace(result_output)
    print(
        json.dumps(
            {
                "status": dataset.status,
                "question_count": dataset.question_count,
                "human_verified_count": dataset.human_verified_count,
                "human_review_required_count": dataset.human_review_required_count,
                "output": str(output),
                "result_output": str(result_output),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


def main() -> None:
    arguments = _arguments()
    asyncio.run(_run(arguments.limit, arguments.output, arguments.result_output))


if __name__ == "__main__":
    main()
