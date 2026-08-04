from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Attachment, Chunk, DataLineage, Document, DocumentVersion, Source


@dataclass(frozen=True, slots=True)
class IndexedChunkRecord:
    chunk_id: str
    document_id: str
    title: str
    content: str
    source_url: str
    source_id: int | None
    source_name: str | None
    official_status: str | None
    region: str | None
    city: str | None
    document_type: str | None
    issuing_authority: str | None
    document_number: str | None
    publish_date: date | None
    document_version: int
    section_path: str | None
    section_title: str | None
    page_number: int | None


class IndexRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_document(self, document_id: int) -> Document | None:
        result = await self.session.execute(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.source))
        )
        return result.scalar_one_or_none()

    async def list_document_chunks(self, document_id: int) -> list[Chunk]:
        result = await self.session.scalars(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
        )
        return list(result)

    async def list_indexable_attachments(self, document_id: int) -> list[Attachment]:
        result = await self.session.scalars(
            select(Attachment)
            .where(
                Attachment.document_id == document_id,
                Attachment.parse_status == "completed",
                Attachment.parsed_text.is_not(None),
            )
            .order_by(Attachment.id)
        )
        return [attachment for attachment in result if attachment.parsed_text]

    async def latest_version_id(self, document_id: int, version: int) -> int | None:
        value = await self.session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version == version,
            )
        )
        return int(value) if value is not None else None

    async def latest_crawl_task_id(self, document_id: int) -> int | None:
        value = await self.session.scalar(
            select(DataLineage.crawl_task_id)
            .where(
                DataLineage.document_id == document_id,
                DataLineage.crawl_task_id.is_not(None),
            )
            .order_by(DataLineage.created_at.desc())
            .limit(1)
        )
        return int(value) if value is not None else None

    async def ensure_document_version(self, document: Document) -> int:
        existing = await self.latest_version_id(document.id, document.version)
        if existing is not None:
            return existing
        snapshot = DocumentVersion(
            document_id=document.id,
            version=document.version,
            content_hash=document.content_hash
            or hashlib.sha256(document.content.encode("utf-8")).hexdigest(),
            content=document.content,
            metadata_json={
                "title": document.title,
                "publish_date": (
                    document.publish_date.isoformat() if document.publish_date else None
                ),
                "issuing_authority": document.issuing_authority,
                "document_number": document.document_number,
                "region": document.region,
                "document_type": document.document_type,
            },
            changed_fields_json=[],
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot.id

    async def replace_chunks(self, document_id: int, chunks: list[Chunk]) -> list[Chunk]:
        existing_ids = list(
            await self.session.scalars(select(Chunk.id).where(Chunk.document_id == document_id))
        )
        if existing_ids:
            await self.session.execute(
                update(DataLineage)
                .where(DataLineage.chunk_id.in_(existing_ids))
                .values(chunk_id=None)
            )
        await self.session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        self.session.add_all(chunks)
        await self.session.flush()
        return chunks

    async def add_lineages(self, lineages: list[DataLineage]) -> None:
        self.session.add_all(lineages)
        await self.session.flush()

    async def set_document_index_status(self, document_id: int, status: str) -> None:
        await self.session.execute(
            update(Document).where(Document.id == document_id).values(index_status=status)
        )

    async def set_chunk_vector_status(self, document_id: int, status: str) -> None:
        await self.session.execute(
            update(Chunk).where(Chunk.document_id == document_id).values(vector_status=status)
        )

    async def orphaned_vector_point_ids(
        self, document_id: int, current_point_ids: set[str]
    ) -> set[str]:
        values = await self.session.scalars(
            select(DataLineage.vector_point_id).where(
                DataLineage.document_id == document_id,
                DataLineage.vector_point_id.is_not(None),
            )
        )
        return {
            str(value)
            for value in values
            if value is not None and str(value) not in current_point_ids
        }

    async def vector_point_ids_for_document(self, document_id: int) -> set[str]:
        """Return live chunk IDs plus historic lineage IDs before a document mutation."""
        chunk_ids = await self.session.scalars(
            select(Chunk.chunk_id).where(Chunk.document_id == document_id)
        )
        lineage_ids = await self.session.scalars(
            select(DataLineage.vector_point_id).where(
                DataLineage.document_id == document_id,
                DataLineage.vector_point_id.is_not(None),
            )
        )
        return {str(value) for value in (*chunk_ids.all(), *lineage_ids.all()) if value is not None}

    async def list_indexed_chunks(self) -> list[IndexedChunkRecord]:
        rows = (
            await self.session.execute(
                select(Chunk, Document, Source)
                .join(Document, Document.id == Chunk.document_id)
                .outerjoin(Source, Source.id == Document.source_id)
                .where(
                    Document.final_status == "approved",
                    Document.index_status == "indexed",
                    Chunk.vector_status == "indexed",
                )
                .order_by(Document.id, Chunk.chunk_index)
            )
        ).all()
        return [
            IndexedChunkRecord(
                chunk_id=chunk.chunk_id,
                document_id=document.document_id,
                title=document.title,
                content=chunk.content,
                source_url=document.source_url,
                source_id=document.source_id,
                source_name=source.name if source is not None else None,
                official_status=source.official_status if source is not None else None,
                region=document.region,
                city=document.city,
                document_type=document.document_type,
                issuing_authority=document.issuing_authority,
                document_number=document.document_number,
                publish_date=document.publish_date,
                document_version=document.version,
                section_path=chunk.section_path,
                section_title=chunk.section_title,
                page_number=chunk.page_number,
            )
            for chunk, document, source in rows
        ]

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
