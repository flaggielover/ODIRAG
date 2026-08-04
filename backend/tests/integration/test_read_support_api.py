from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import httpx

from app.models import (
    Attachment,
    Document,
    DocumentReview,
    DocumentVersion,
    QueryTrace,
    Source,
)


async def test_document_read_endpoints_require_admin_and_load_filtered_details(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    async with app.state.database.session_factory() as session:
        primary_source = Source(
            source_key="document-read-primary",
            name="Primary source",
            domain="primary.gov",
            homepage_url="https://primary.gov/",
            official_status="official",
        )
        other_source = Source(
            source_key="document-read-other",
            name="Other source",
            domain="other.gov",
            homepage_url="https://other.gov/",
            official_status="official",
        )
        document = Document(
            document_id="DOC-BUDGET-2026",
            source=primary_source,
            title="Regional budget policy",
            subtitle="Implementation details",
            source_url="https://primary.gov/policies/budget",
            canonical_url="https://primary.gov/policies/budget-canonical",
            publish_date=date(2026, 6, 1),
            author="Policy office",
            issuing_authority="Regional Government",
            document_number="BUDGET-2026-01",
            region="Sichuan",
            city="Chengdu",
            document_type="budget_policy",
            content="Approved budget policy content.",
            raw_content="<p>Approved budget policy content.</p>",
            content_hash="content-hash-v2",
            simhash="abc123",
            word_count=5,
            language="en",
            quality_score=Decimal("0.9400"),
            rule_filter_status="approved",
            llm_review_status="approved",
            manual_review_status="approved",
            final_status="approved",
            index_status="indexed",
            version=2,
        )
        document.versions.append(
            DocumentVersion(
                version=2,
                content_hash="content-hash-v2",
                content="Approved budget policy content.",
                metadata_json={"title": "Regional budget policy"},
                changed_fields_json=["content"],
            )
        )
        document.attachments.append(
            Attachment(
                attachment_name="budget.pdf",
                source_url="https://primary.gov/files/budget.pdf",
                mime_type="application/pdf",
                file_extension="pdf",
                file_size=2048,
                file_hash="attachment-hash",
                download_status="completed",
                parse_status="completed",
                parsed_text="Attachment text",
                page_count=3,
                requires_ocr=False,
            )
        )
        document.reviews.append(
            DocumentReview(
                review_type="manual",
                reviewer="admin",
                decision="approve",
                quality_score=Decimal("0.9500"),
                document_type="budget_policy",
                topics_json=["budget"],
                summary="Approved after verification",
                reasons_json=["official source"],
                extracted_fields_json={"authority": "Regional Government"},
                prompt_version="manual-v1",
            )
        )
        other_document = Document(
            document_id="DOC-OTHER-2026",
            source=other_source,
            title="Unrelated education notice",
            source_url="https://other.gov/notices/education",
            content="Rejected notice.",
            word_count=2,
            final_status="rejected",
            index_status="failed",
        )
        session.add_all([document, other_document])
        await session.commit()
        await session.refresh(document)
        await session.refresh(primary_source)
        await session.refresh(other_source)
        document_id = document.id
        source_id = primary_source.id
        other_source_id = other_source.id

    assert (await client.get("/api/documents")).status_code == 401
    assert (await client.get(f"/api/documents/{document_id}")).status_code == 401

    listed = await client.get(
        "/api/documents",
        headers=auth_headers,
        params={
            "final_status": "approved",
            "index_status": "indexed",
            "source_id": source_id,
            "q": "budget",
            "limit": 1,
        },
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    summary = listed.json()[0]
    assert summary["id"] == document_id
    assert summary["document_id"] == "DOC-BUDGET-2026"
    assert summary["source"]["source_key"] == "document-read-primary"

    filter_cases = [
        ({"final_status": "rejected"}, "DOC-OTHER-2026"),
        ({"index_status": "failed"}, "DOC-OTHER-2026"),
        ({"source_id": other_source_id}, "DOC-OTHER-2026"),
        ({"q": "education"}, "DOC-OTHER-2026"),
    ]
    for params, expected_document_id in filter_cases:
        filtered = await client.get("/api/documents", headers=auth_headers, params=params)
        assert filtered.status_code == 200
        assert [item["document_id"] for item in filtered.json()] == [expected_document_id]

    limited = await client.get("/api/documents", headers=auth_headers, params={"limit": 1})
    assert limited.status_code == 200
    assert len(limited.json()) == 1

    detail = await client.get(f"/api/documents/{document_id}", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["subtitle"] == "Implementation details"
    assert body["canonical_url"].endswith("budget-canonical")
    assert body["content"] == "Approved budget policy content."
    assert body["raw_content"].startswith("<p>")
    assert body["source"]["domain"] == "primary.gov"
    assert body["versions"][0]["version"] == 2
    assert body["attachments"][0]["attachment_name"] == "budget.pdf"
    assert body["reviews"][0]["decision"] == "approve"

    missing = await client.get("/api/documents/999999", headers=auth_headers)
    assert missing.status_code == 404


async def test_trace_list_requires_authentication_and_supports_filters(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    async with app.state.database.session_factory() as session:
        included_trace_id = str(uuid.uuid4())
        session.add_all(
            [
                QueryTrace(
                    trace_id=included_trace_id,
                    user_query="Summarize the budget policy",
                    query_type="rag",
                    prompt_version="v1",
                    prompt_snapshot_json={"version": "v1", "content": "grounded"},
                    answer="Budget summary",
                    refusal=False,
                    latency_ms=25,
                    cost=Decimal("0.01000000"),
                ),
                QueryTrace(
                    trace_id=str(uuid.uuid4()),
                    user_query="Count approved policies",
                    query_type="sql",
                    prompt_version="v1",
                    prompt_snapshot_json={"version": "v1", "content": "structured"},
                    answer="No answer",
                    refusal=True,
                    latency_ms=10,
                    cost=Decimal("0"),
                ),
            ]
        )
        await session.commit()

    assert (await client.get("/api/chat/traces")).status_code == 401

    response = await client.get(
        "/api/chat/traces",
        headers=auth_headers,
        params={"limit": 1, "query_type": "rag", "refusal": "false"},
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    trace = response.json()[0]
    assert trace["trace_id"] == included_trace_id
    assert trace["query_type"] == "rag"
    assert trace["refusal"] is False

    sql_only = await client.get(
        "/api/chat/traces", headers=auth_headers, params={"query_type": "sql"}
    )
    assert sql_only.status_code == 200
    assert [item["query_type"] for item in sql_only.json()] == ["sql"]

    refusals = await client.get(
        "/api/chat/traces", headers=auth_headers, params={"refusal": "true"}
    )
    assert refusals.status_code == 200
    assert [item["refusal"] for item in refusals.json()] == [True]

    limited = await client.get("/api/chat/traces", headers=auth_headers, params={"limit": 1})
    assert limited.status_code == 200
    assert len(limited.json()) == 1

    invalid_type = await client.get(
        "/api/chat/traces",
        headers=auth_headers,
        params={"query_type": "unsupported"},
    )
    assert invalid_type.status_code == 422


async def test_document_mutations_version_and_remove_retrieval_artifacts(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    async with app.state.database.session_factory() as session:
        document = Document(
            document_id="DOC-MUTATION-2026",
            title="Original policy title",
            source_url="https://example.gov/policy",
            raw_content="<h1>Original policy title</h1><p>Approved policy content.</p>",
            content="Approved policy content.",
            content_hash="original-content-hash",
            word_count=3,
            final_status="approved",
            index_status="pending",
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        document_id = document.id

    indexed = await client.post(f"/api/documents/{document_id}/reindex", headers=auth_headers)
    assert indexed.status_code == 200
    runtime = app.state.runtime
    assert runtime.vector_store.point_count == 1
    assert runtime.bm25_index.document_count == 1

    updated = await client.put(
        f"/api/documents/{document_id}",
        headers=auth_headers,
        json={"title": "Corrected policy title"},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["index_status"] == "stale"
    assert [item["version"] for item in updated.json()["versions"]] == [1, 2]
    assert runtime.vector_store.point_count == 0
    assert runtime.bm25_index.document_count == 0

    unknown_field = await client.put(
        f"/api/documents/{document_id}",
        headers=auth_headers,
        json={"final_status": "approved"},
    )
    assert unknown_field.status_code == 422

    unchanged = await client.put(
        f"/api/documents/{document_id}",
        headers=auth_headers,
        json={"title": "Corrected policy title"},
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["version"] == 2

    reindexed = await client.post(f"/api/documents/{document_id}/reindex", headers=auth_headers)
    assert reindexed.status_code == 200
    assert runtime.vector_store.point_count == 1
    assert runtime.bm25_index.document_count == 1

    deleted = await client.delete(f"/api/documents/{document_id}", headers=auth_headers)
    assert deleted.status_code == 204
    assert runtime.vector_store.point_count == 0
    assert runtime.bm25_index.document_count == 0
    assert (
        await client.get(f"/api/documents/{document_id}", headers=auth_headers)
    ).status_code == 404


async def test_reparse_invalidates_existing_retrieval_artifacts(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    async with app.state.database.session_factory() as session:
        document = Document(
            document_id="DOC-REPARSE-2026",
            title="Reparse policy",
            source_url="https://example.gov/reparse",
            raw_content="<h1>Reparse policy</h1><p>Original content.</p>",
            content="Original content.",
            content_hash="old-content-hash",
            word_count=2,
            final_status="approved",
            index_status="pending",
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        document_id = document.id

    assert (
        await client.post(f"/api/documents/{document_id}/reindex", headers=auth_headers)
    ).status_code == 200
    runtime = app.state.runtime
    assert runtime.vector_store.point_count == 1
    assert runtime.bm25_index.document_count == 1

    async with app.state.database.session_factory() as session:
        persisted = await session.get(Document, document_id)
        assert persisted is not None
        persisted.raw_content = "<h1>Reparse policy</h1><p>Changed content.</p>"
        await session.commit()

    reparsed = await client.post(f"/api/documents/{document_id}/reparse", headers=auth_headers)
    assert reparsed.status_code == 200
    assert reparsed.json()["index_status"] == "stale"
    assert runtime.vector_store.point_count == 0
    assert runtime.bm25_index.document_count == 0
