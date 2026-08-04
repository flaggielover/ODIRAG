from __future__ import annotations

import uuid

import httpx
from sqlalchemy import func, select

from app.models import Document, EvaluationQuestion, QueryTrace, Source


async def test_feedback_lifecycle_and_evaluation_conversion(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    trace_id = str(uuid.uuid4())
    public_document_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key=f"feedback-source-{uuid.uuid4()}",
            name="Feedback Government",
            domain="feedback.gov",
            homepage_url="https://feedback.gov/",
            official_status="official",
        )
        document = Document(
            document_id=public_document_id,
            source=source,
            title="Feedback policy",
            source_url="https://feedback.gov/policy",
            content="Verified policy evidence.",
            word_count=3,
            final_status="approved",
        )
        trace = QueryTrace(
            trace_id=trace_id,
            user_query="Which verified support condition is missing?",
            query_type="rag",
            parsed_filters_json={"region": "Sichuan"},
            citations_json=[
                {
                    "document_id": public_document_id,
                    "chunk_id": chunk_id,
                    "quote": "Verified policy evidence.",
                }
            ],
            final_context_json=[{"chunk_id": chunk_id}],
            answer="Partial answer",
        )
        session.add_all([document, trace])
        await session.commit()
        await session.refresh(document)
        database_document_id = document.id

    missing_document = await client.post(
        "/api/feedback",
        headers=auth_headers,
        json={
            "trace_id": trace_id,
            "feedback_type": "missing_document",
        },
    )
    assert missing_document.status_code == 422

    created = await client.post(
        "/api/feedback",
        headers=auth_headers,
        json={
            "trace_id": trace_id,
            "feedback_type": "incomplete_answer",
            "rating": 2,
            "comment": "The application deadline is missing.",
            "expected_document_id": database_document_id,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["resolved"] is False
    assert body["converted_to_evaluation"] is False
    feedback_id = body["id"]

    unauthorized = await client.get("/api/feedback")
    assert unauthorized.status_code == 401

    listing = await client.get(
        "/api/feedback",
        headers=auth_headers,
        params={"feedback_type": "incomplete_answer", "resolved": False},
    )
    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [feedback_id]

    converted = await client.post(
        f"/api/feedback/{feedback_id}/convert-to-evaluation",
        headers=auth_headers,
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["resolved"] is True
    assert converted.json()["converted_to_evaluation"] is True

    repeated = await client.post(
        f"/api/feedback/{feedback_id}/convert-to-evaluation",
        headers=auth_headers,
    )
    assert repeated.status_code == 200

    async with app.state.database.session_factory() as session:
        question = await session.scalar(
            select(EvaluationQuestion).where(
                EvaluationQuestion.question_id == f"feedback-{feedback_id}"
            )
        )
        count = await session.scalar(
            select(func.count())
            .select_from(EvaluationQuestion)
            .where(EvaluationQuestion.question_id == f"feedback-{feedback_id}")
        )
    assert question is not None
    assert question.verified is True
    assert question.question == "Which verified support condition is missing?"
    assert question.expected_document_ids == [public_document_id]
    assert question.expected_chunk_ids == [chunk_id]
    assert question.expected_answer_points == ["The application deadline is missing."]
    assert question.expected_filters == {"region": "Sichuan"}
    assert count == 1

    helpful = await client.post(
        "/api/feedback",
        headers=auth_headers,
        json={
            "trace_id": trace_id,
            "feedback_type": "helpful",
            "rating": 5,
        },
    )
    assert helpful.status_code == 201
    rejected_conversion = await client.post(
        f"/api/feedback/{helpful.json()['id']}/convert-to-evaluation",
        headers=auth_headers,
    )
    assert rejected_conversion.status_code == 409
