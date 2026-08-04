from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.models import Chunk, CrawlTask, DataLineage, Document, Source, SourceColumn
from app.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorPoint


async def test_vector_store_count_uses_payload_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = InMemoryVectorStore()
    await memory.upsert(
        [
            VectorPoint("p1", [1.0], "doc-1", "one", "One", "https://example.com/1"),
            VectorPoint("p2", [1.0], "doc-1", "two", "Two", "https://example.com/2"),
            VectorPoint("p3", [1.0], "doc-2", "three", "Three", "https://example.com/3"),
        ]
    )
    assert await memory.count() == 3
    assert await memory.count({"document_id": "doc-1"}) == 2

    calls: dict[str, object] = {}

    class FakeClient:
        async def count(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(count=7)

        async def close(self) -> None:
            return None

    qdrant = QdrantVectorStore(url="http://qdrant.test", collection_name="chunks")
    monkeypatch.setattr(qdrant, "_client", lambda: FakeClient())
    assert await qdrant.count({"document_id": "doc-1"}) == 7
    assert calls["collection_name"] == "chunks"
    assert calls["exact"] is True
    assert calls["count_filter"] is not None


async def _seed_acceptance_task(app) -> int:
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key=f"acceptance-{uuid.uuid4().hex}",
            name="Acceptance source",
            domain="example.com",
            homepage_url="https://example.com/",
            crawl_provider="local",
        )
        column = SourceColumn(
            source=source,
            column_key="notices",
            column_name="Notices",
            column_url="https://example.com/notices",
            request_interval_seconds=0,
        )
        task = CrawlTask(
            source_column=column,
            status="completed",
            crawl_provider="local",
            provider="local",
            current_stage="completed",
        )
        document = Document(
            document_id="acceptance-doc-1",
            source=source,
            source_column=column,
            title="Acceptance document",
            source_url="https://example.com/notices/1",
            canonical_url="https://example.com/notices/1",
            content="acceptance content",
            word_count=18,
            final_status="approved",
            index_status="indexed",
            first_crawl_time=datetime.now(UTC),
            last_crawl_time=datetime.now(UTC),
        )
        session.add_all([source, column, task, document])
        await session.flush()
        for index in range(2):
            content = f"chunk-{index}"
            session.add(
                Chunk(
                    chunk_id=f"acceptance-chunk-{index}-{uuid.uuid4().hex}",
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                    char_count=len(content),
                    token_count=1,
                    vector_status="indexed",
                )
            )
        session.add(
            DataLineage(
                lineage_id=str(uuid.uuid4()),
                source_id=source.id,
                crawl_task_id=task.id,
                document_id=document.id,
            )
        )
        await session.commit()
        return task.id


async def test_acceptance_summary_counts_database_chunks_and_real_vector_points(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    task_id = await _seed_acceptance_task(app)
    store = app.state.runtime.vector_store
    await store.upsert(
        [
            VectorPoint(
                "acceptance-point-1",
                [1.0] * 8,
                "acceptance-doc-1",
                "one",
                "One",
                "https://example.com/1",
            ),
            VectorPoint(
                "acceptance-point-2",
                [1.0] * 8,
                "acceptance-doc-1",
                "two",
                "Two",
                "https://example.com/2",
            ),
            VectorPoint(
                "unrelated-point",
                [1.0] * 8,
                "another-document",
                "other",
                "Other",
                "https://example.com/other",
            ),
        ]
    )

    unauthorized = await client.get(f"/api/crawl-tasks/{task_id}/acceptance-summary")
    assert unauthorized.status_code == 401
    missing = await client.get("/api/crawl-tasks/999999/acceptance-summary", headers=auth_headers)
    assert missing.status_code == 404

    response = await client.get(
        f"/api/crawl-tasks/{task_id}/acceptance-summary", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == {
        "crawl_task_id": task_id,
        "database_document_count": 1,
        "chunk_count": 2,
        "qdrant_point_count": 2,
    }
