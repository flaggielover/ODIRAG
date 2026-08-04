from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import func, select

from app.models import DataLineage, Document, Source, SourceColumn


async def test_real_demo_evaluation_writes_reports_and_persists_metrics(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key=f"evaluation-source-{uuid.uuid4()}",
            name="Evaluation Government",
            domain="evaluation.gov",
            homepage_url="https://evaluation.gov/",
            official_status="official",
        )
        column = SourceColumn(
            source=source,
            column_key="policies",
            column_name="Policies",
            column_url="https://evaluation.gov/policies",
            request_interval_seconds=0,
        )
        document = Document(
            document_id=str(uuid.uuid4()),
            source=source,
            source_column=column,
            title="Software research support policy",
            source_url="https://evaluation.gov/policies/research-support",
            publish_date=date(2026, 2, 1),
            content="# Support measures\n\nSoftware companies can apply for research funding.",
            word_count=9,
            final_status="approved",
            index_status="pending",
            version=1,
            document_type="industry_policy",
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        database_id = document.id
        public_id = document.document_id

    indexed = await client.post(
        f"/api/documents/{database_id}/reindex",
        headers=auth_headers,
    )
    assert indexed.status_code == 200
    chunk_id = indexed.json()["vector_point_ids"][0]

    unauthorized = await client.post(
        "/api/evaluations/run",
        json={"run_name": "unauthorized"},
    )
    assert unauthorized.status_code == 401

    response = await client.post(
        "/api/evaluations/run",
        headers=auth_headers,
        json={
            "run_name": "real-demo-evaluation",
            "questions": [
                {
                    "question_id": f"demo-answer-{uuid.uuid4()}",
                    "question": "What research support can software companies apply for?",
                    "query_type": "rag",
                    "expected_document_ids": [public_id],
                    "expected_chunk_ids": [chunk_id],
                    "expected_answer_points": ["Software companies can apply for research funding"],
                    "difficulty": "easy",
                    "category": "support",
                    "created_by": "integration-test",
                    "verified": True,
                },
                {
                    "question_id": f"demo-refusal-{uuid.uuid4()}",
                    "question": "What is the current weather on Mars?",
                    "query_type": "rag",
                    "should_refuse": True,
                    "difficulty": "easy",
                    "category": "refusal",
                    "created_by": "integration-test",
                    "verified": True,
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question_count"] == 2
    assert float(body["recall_at_1"]) == 1.0
    assert float(body["citation_accuracy"]) == 1.0
    assert float(body["refusal_accuracy"]) == 1.0
    assert float(body["hallucination_rate"]) == 0.0
    run_id = body["id"]

    async with app.state.database.session_factory() as session:
        lineage_count = await session.scalar(
            select(func.count())
            .select_from(DataLineage)
            .where(DataLineage.evaluation_run_id == run_id)
        )
    assert int(lineage_count or 0) >= 1

    listing = await client.get("/api/evaluations", headers=auth_headers)
    assert listing.status_code == 200
    assert any(item["id"] == run_id for item in listing.json())

    detail = await client.get(f"/api/evaluations/{run_id}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["run_name"] == "real-demo-evaluation"

    report = await client.get(
        f"/api/evaluations/{run_id}/report",
        headers=auth_headers,
    )
    assert report.status_code == 200, report.text
    report_body = report.json()
    assert report_body["aggregate"]["document_hit_rate"] == 1.0
    assert report_body["aggregate"]["chunk_hit_rate"] == 1.0
    assert report_body["aggregate"]["answer_point_coverage"] == 1.0
    assert report_body["aggregate"]["citation_completeness"] == 1.0
    assert report_body["aggregate"]["hallucination_assessed_claims"] >= 1
    assert len(report_body["questions"]) == 2
    for artifact in report_body["artifacts"].values():
        assert _is_file(artifact)


def _is_file(path: str) -> bool:
    return Path(path).is_file()
