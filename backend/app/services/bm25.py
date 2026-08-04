from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio

from app.bm25 import BM25Document, BM25Index
from app.repositories.indexing import IndexedChunkRecord, IndexRepository


@dataclass(frozen=True, slots=True)
class BM25RebuildResult:
    document_count: int
    snapshot_path: Path


class BM25RebuildService:
    def __init__(self, repository: IndexRepository) -> None:
        self.repository = repository

    async def rebuild(self, snapshot_path: Path) -> BM25RebuildResult:
        index = await self.build_index()
        await anyio.to_thread.run_sync(index.save, snapshot_path)
        return BM25RebuildResult(index.document_count, snapshot_path)

    async def build_index(self) -> BM25Index:
        records = await self.repository.list_indexed_chunks()
        index = BM25Index()
        index.rebuild([self._document(record) for record in records])
        return index

    @staticmethod
    def _document(record: IndexedChunkRecord) -> BM25Document:
        metadata: dict[str, Any] = {
            "source_id": record.source_id,
            "source_name": record.source_name,
            "official_status": record.official_status,
            "region": record.region,
            "city": record.city,
            "document_type": record.document_type,
            "issuing_authority": record.issuing_authority,
            "document_number": record.document_number,
            "publish_date": (record.publish_date.isoformat() if record.publish_date else None),
            "document_version": record.document_version,
            "section_path": record.section_path,
            "section_title": record.section_title,
            "page_number": record.page_number,
        }
        return BM25Document(
            chunk_id=record.chunk_id,
            document_id=record.document_id,
            title=record.title,
            content=record.content,
            source_url=record.source_url,
            metadata={key: value for key, value in metadata.items() if value is not None},
        )
