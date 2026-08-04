from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Attachment, DataLineage, Document, DocumentVersion


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, document_id: int) -> Document | None:
        return await self.session.get(Document, document_id)

    async def list(
        self,
        *,
        final_status: str | None = None,
        index_status: str | None = None,
        source_id: int | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[Document]:
        statement = select(Document).options(selectinload(Document.source))
        if final_status is not None:
            statement = statement.where(Document.final_status == final_status)
        if index_status is not None:
            statement = statement.where(Document.index_status == index_status)
        if source_id is not None:
            statement = statement.where(Document.source_id == source_id)
        if query is not None and (term := query.strip()):
            pattern = f"%{term}%"
            statement = statement.where(
                or_(
                    Document.document_id.ilike(pattern),
                    Document.title.ilike(pattern),
                    Document.source_url.ilike(pattern),
                    Document.issuing_authority.ilike(pattern),
                    Document.document_number.ilike(pattern),
                )
            )
        result = await self.session.execute(
            statement.order_by(Document.updated_at.desc(), Document.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_detail(self, document_id: int) -> Document | None:
        result = await self.session.execute(
            select(Document)
            .options(
                selectinload(Document.source),
                selectinload(Document.versions),
                selectinload(Document.attachments),
                selectinload(Document.reviews),
            )
            .execution_options(populate_existing=True)
            .where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def get_lineage(self, document_id: int) -> Document | None:
        result = await self.session.execute(
            select(Document)
            .options(selectinload(Document.lineage_records))
            .where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def get_attachment(self, attachment_id: int) -> Attachment | None:
        return await self.session.get(Attachment, attachment_id)

    async def version_count(self, document_id: int) -> int:
        count = await self.session.scalar(
            select(func.count())
            .select_from(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
        )
        return int(count or 0)

    async def add_version(self, version: DocumentVersion) -> DocumentVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def add_lineage(self, lineage: DataLineage) -> DataLineage:
        self.session.add(lineage)
        await self.session.flush()
        return lineage

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def delete(self, document: Document) -> None:
        await self.session.delete(document)
        await self.session.commit()
