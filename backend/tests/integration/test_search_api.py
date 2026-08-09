from __future__ import annotations

import uuid
from datetime import date

import httpx

from app.models import CrawlTask, DataLineage, Document, Source, SourceColumn


async def test_reindex_and_search_debug_use_real_shared_indexes(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key="search-api-source",
            name="Search API source",
            domain="search.gov",
            homepage_url="https://search.gov/",
            official_status="official",
        )
        column = SourceColumn(
            source=source,
            column_key="policies",
            column_name="Policies",
            column_url="https://search.gov/policies",
            request_interval_seconds=0,
        )
        document = Document(
            document_id=str(uuid.uuid4()),
            source=source,
            source_column=column,
            title="四川软件企业研发支持政策",
            source_url="https://search.gov/policies/1",
            publish_date=date(2026, 2, 1),
            content="# 支持措施\n\n四川软件企业研发投入可以申请资金补助。",
            word_count=24,
            final_status="approved",
            index_status="pending",
            version=1,
            region="四川",
            document_type="产业政策",
        )
        crawl_task = CrawlTask(
            source_column=column,
            task_type="full",
            trigger_type="manual",
            status="completed",
            discovered_count=1,
            fetched_count=1,
            success_count=1,
        )
        session.add_all([document, crawl_task])
        await session.flush()
        session.add(
            DataLineage(
                lineage_id=str(uuid.uuid4()),
                source_id=source.id,
                crawl_task_id=crawl_task.id,
                document_id=document.id,
            )
        )
        await session.commit()
        await session.refresh(document)
        database_id = document.id
        public_id = document.document_id

    unauthorized = await client.post(f"/api/documents/{database_id}/reindex")
    assert unauthorized.status_code == 401

    indexed = await client.post(
        f"/api/documents/{database_id}/reindex",
        headers=auth_headers,
    )
    assert indexed.status_code == 200
    assert indexed.json()["chunk_count"] >= 1
    assert indexed.json()["bm25_document_count"] >= 1

    chunks = await client.get(
        f"/api/documents/{database_id}/chunks",
        headers=auth_headers,
    )
    assert chunks.status_code == 200
    assert chunks.json()[0]["vector_status"] == "indexed"

    debug = await client.post(
        "/api/search/debug",
        headers=auth_headers,
        json={
            "query": "四川 2025之后 软件研发资金",
            "mode": "hybrid_rerank",
            "filters": {"document_type": "产业政策"},
        },
    )
    assert debug.status_code == 200
    body = debug.json()
    assert body["hits"][0]["document_id"] == public_id
    assert body["analysis"]["inferred_filters"]["publish_date_gte"] == "2026-01-01"
    assert body["bm25_results"]
    assert body["vector_results"]
    assert body["fusion_results"]
    assert body["rerank_results"]
    assert body["timings_ms"]["total"] >= 0

    regular = await client.post(
        "/api/search",
        headers=auth_headers,
        json={"query": "软件研发资金", "mode": "hybrid"},
    )
    assert regular.status_code == 200
    assert regular.json()["hits"][0]["document_id"] == public_id

    invalid = await client.post(
        "/api/search/debug",
        headers=auth_headers,
        json={"query": "政策", "filters": {"unknown": "value"}},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_SEARCH_REQUEST"

    composite = await client.post(
        "/api/chat",
        headers=auth_headers,
        json={"query": "四川 2025之后的软件企业有哪些支持措施？"},
    )
    assert composite.status_code == 200
    chat_body = composite.json()
    assert chat_body["query_type"] == "sql+rag"
    assert chat_body["structured_count"] == 1
    assert chat_body["refusal"] is False
    assert chat_body["evidence_sufficiency"]["sufficient"] is True
    assert chat_body["evidence_sufficiency"]["supported_chunk_ids"]
    assert chat_body["citations"][0]["document_id"] == public_id
    assert chat_body["citations"][0]["url"] == "https://search.gov/policies/1"

    trace = await client.get(
        f"/api/chat/traces/{chat_body['trace_id']}",
        headers=auth_headers,
    )
    assert trace.status_code == 200
    assert trace.json()["final_context_json"]
    assert trace.json()["prompt_snapshot_json"]["content"]
    assert trace.json()["evidence_decision_json"]["status"] == "passed"
    assert trace.json()["citations_json"][0]["chunk_id"] == chat_body["citations"][0]["chunk_id"]

    lineage = await client.get(
        f"/api/chat/traces/{chat_body['trace_id']}/lineage",
        headers=auth_headers,
    )
    assert lineage.status_code == 200
    chain = lineage.json()["citations"][0]
    assert chain["complete"] is True
    assert chain["chunk"]["chunk_id"] == chat_body["citations"][0]["chunk_id"]
    assert chain["document"]["document_id"] == public_id
    assert chain["document_version"]["version"] == 1
    assert chain["crawl_task"]["id"] == crawl_task.id
    assert chain["source"]["source_key"] == "search-api-source"

    sql_answer = await client.post(
        "/api/chat",
        headers=auth_headers,
        json={"query": "四川 2025之后有多少份政策？"},
    )
    assert sql_answer.status_code == 200
    assert sql_answer.json()["query_type"] == "sql"
    assert sql_answer.json()["structured_count"] == 1
    assert "1" in sql_answer.json()["answer"]

    refusal = await client.post(
        "/api/chat",
        headers=auth_headers,
        json={"query": "火星天气如何？"},
    )
    assert refusal.status_code == 200
    assert refusal.json()["refusal"] is True
    assert refusal.json()["refusal_reasons"]
    assert refusal.json()["citations"] == []
    assert refusal.json()["evidence_sufficiency"]["sufficient"] is False
