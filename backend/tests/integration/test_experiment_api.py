from __future__ import annotations

import uuid
from pathlib import Path

import httpx

from app.models import Document, Source, SourceColumn


async def test_experiment_api_runs_real_variants_and_reports_regressions(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key=f"experiment-source-{uuid.uuid4()}",
            name="Experiment Government",
            domain="experiment.gov",
            homepage_url="https://experiment.gov/",
            official_status="official",
        )
        column = SourceColumn(
            source=source,
            column_key="policies",
            column_name="Policies",
            column_url="https://experiment.gov/policies",
            request_interval_seconds=0,
        )
        document = Document(
            document_id=str(uuid.uuid4()),
            source=source,
            source_column=column,
            title="Software innovation policy",
            source_url="https://experiment.gov/policies/innovation",
            content="# Support\n\nSoftware companies can apply for innovation grants.",
            word_count=8,
            final_status="approved",
            index_status="pending",
            version=1,
            region="Sichuan",
            document_type="industry_policy",
        )
        session.add(document)
        await session.commit()
        public_id = document.document_id

    name = f"retrieval_regression_{uuid.uuid4().hex}"
    created = await client.post(
        "/api/experiments",
        headers=auth_headers,
        json={
            "experiment_name": name,
            "experiment_type": "retrieval",
            "baseline_config": {
                "chunking": {
                    "target_chars": 600,
                    "min_chars": 160,
                    "max_chars": 900,
                    "overlap_chars": 100,
                },
                "top_k": 5,
                "rerank": "deterministic",
                "prompt_version": "baseline-v1",
            },
            "candidate_config": {
                "chunking": {
                    "target_chars": 800,
                    "min_chars": 160,
                    "max_chars": 1200,
                    "overlap_chars": 120,
                },
                "top_k": 5,
                "rrf_k": 30,
                "rerank": False,
                "score_threshold": 0.0,
                "metadata_filters": {"region": "Missing Region"},
                "prompt_version": "candidate-v2",
            },
        },
    )
    assert created.status_code == 200, created.text
    experiment_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    unauthorized = await client.post(
        f"/api/experiments/{experiment_id}/run",
        json={},
    )
    assert unauthorized.status_code == 401

    executed = await client.post(
        f"/api/experiments/{experiment_id}/run",
        headers=auth_headers,
        json={
            "questions": [
                {
                    "question_id": f"experiment-question-{uuid.uuid4()}",
                    "question": "What grants can software companies apply for?",
                    "query_type": "rag",
                    "expected_document_ids": [public_id],
                    "expected_answer_points": [
                        "Software companies can apply for innovation grants"
                    ],
                    "difficulty": "easy",
                    "category": "experiment",
                    "created_by": "integration-test",
                    "verified": True,
                }
            ]
        },
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "completed"
    assert "Regression detected" in executed.json()["conclusion"]

    listing = await client.get("/api/experiments", headers=auth_headers)
    assert listing.status_code == 200
    assert any(item["id"] == experiment_id for item in listing.json())

    detail = await client.get(f"/api/experiments/{experiment_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["experiment_name"] == name

    comparison = await client.get(
        f"/api/experiments/{experiment_id}/compare",
        headers=auth_headers,
    )
    assert comparison.status_code == 200, comparison.text
    body = comparison.json()
    assert body["has_regression"] is True
    assert body["regressions"]
    assert body["failed_cases"][0]["new_regression"] is True
    assert (
        body["baseline"]["metadata"]["evaluation_run_id"]
        != body["candidate"]["metadata"]["evaluation_run_id"]
    )
    for artifact in body["artifacts"].values():
        assert _is_file(artifact)


def _is_file(path: str) -> bool:
    return Path(path).is_file()
