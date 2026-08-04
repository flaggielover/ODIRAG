from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.bm25 import BM25Index
from app.cache import InMemoryEmbeddingCache
from app.chunking import ChunkingConfig, HeadingAwareChunker
from app.embedding import DeterministicEmbeddingProvider, EmbeddingBatcher
from app.models import (
    Attachment,
    Chunk,
    DataLineage,
    Document,
    DocumentVersion,
    Source,
    SourceColumn,
)
from app.providers import ProviderUnavailableError
from app.repositories.indexing import IndexRepository
from app.services.bm25 import BM25RebuildService
from app.services.indexing import IndexingService
from app.vector_store import InMemoryVectorStore


class FailOnceDeleteVectorStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_delete = False

    async def delete(self, point_ids: list[str]) -> None:
        if self.fail_next_delete:
            self.fail_next_delete = False
            raise ProviderUnavailableError("vector_store", "temporary delete failure")
        await super().delete(point_ids)


async def test_approved_document_indexes_idempotently_and_rebuilds_bm25(app) -> None:
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key="index-source",
            name="Index source",
            domain="index.gov",
            homepage_url="https://index.gov/",
            official_status="official",
        )
        column = SourceColumn(
            source=source,
            column_key="policies",
            column_name="Policies",
            column_url="https://index.gov/policies",
            request_interval_seconds=0,
        )
        document = Document(
            document_id=str(uuid.uuid4()),
            source=source,
            source_column=column,
            title="软件产业支持政策",
            source_url="https://index.gov/policies/1",
            content="# 申报条件\n\n企业应在四川注册。" * 8
            + "\n\n# 支持措施\n\n研发投入可获补助。" * 8,
            word_count=200,
            final_status="approved",
            index_status="pending",
            version=1,
            region="四川",
            document_type="产业政策",
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        attachment = Attachment(
            document_id=document.id,
            attachment_name="申报指南.pdf",
            source_url="https://index.gov/policies/1/guide.pdf",
            parse_status="completed",
            parsed_text="第一页申请材料。\f第二页办理流程。",
            page_count=2,
        )
        session.add(attachment)
        await session.commit()

        provider = DeterministicEmbeddingProvider(dimensions=8)
        store = FailOnceDeleteVectorStore()
        service = IndexingService(
            IndexRepository(session),
            HeadingAwareChunker(
                ChunkingConfig(
                    target_chars=80,
                    min_chars=20,
                    max_chars=120,
                    overlap_chars=10,
                )
            ),
            EmbeddingBatcher(provider, InMemoryEmbeddingCache(), batch_size=2),
            store,
            dimensions=8,
            embedding_version="test-v1",
        )

        first = await service.index_document(document.id)
        second = await service.index_document(document.id)
        assert first.chunk_count > 1
        assert first.vector_point_ids == second.vector_point_ids
        assert second.cache_hits == second.chunk_count
        assert second.embedded_count == 0
        assert store.point_count == second.chunk_count

        stored_chunk_count = await session.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id)
        )
        lineage_count = await session.scalar(
            select(func.count())
            .select_from(DataLineage)
            .where(DataLineage.document_id == document.id)
        )
        await session.refresh(document)
        assert document.index_status == "indexed"
        assert stored_chunk_count == second.chunk_count
        assert lineage_count == first.chunk_count
        version_count = await session.scalar(
            select(func.count())
            .select_from(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
        )
        assert version_count == 1
        attachment_chunks = list(
            await session.scalars(
                select(Chunk).where(
                    Chunk.document_id == document.id,
                    Chunk.attachment_id == attachment.id,
                )
            )
        )
        assert {chunk.page_number for chunk in attachment_chunks} == {1, 2}

        old_point_ids = store.point_ids
        document.version = 2
        document.content = "# 新版本\n\n软件企业可获得新的研发资金支持。" * 5
        document.index_status = "stale"
        await session.commit()
        store.fail_next_delete = True
        with pytest.raises(ProviderUnavailableError, match="temporary delete failure"):
            await service.index_document(document.id)
        await session.refresh(document)
        assert document.index_status == "failed"
        third = await service.index_document(document.id)
        assert old_point_ids.isdisjoint(third.vector_point_ids)
        assert store.point_count == third.chunk_count

        snapshot = Path(".test-data") / "phase5" / f"{uuid.uuid4()}-bm25.json"
        rebuild = await BM25RebuildService(IndexRepository(session)).rebuild(snapshot)
        restored = BM25Index.load(snapshot)
        hits = restored.search("软件研发资金", 5, {"region": "四川"})
        assert rebuild.document_count == third.chunk_count
        assert restored.document_count == third.chunk_count
        assert hits
        assert hits[0].document_id == document.document_id
