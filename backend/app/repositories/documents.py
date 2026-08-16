from __future__ import annotations

import builtins

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Attachment,
    DataLineage,
    Document,
    DocumentMetadataCorrection,
    DocumentReview,
    DocumentVersion,
)


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
    ) -> builtins.list[Document]:
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
        return builtins.list(result.scalars().all())

    async def get_detail(self, document_id: int) -> Document | None:
        result = await self.session.execute(
            select(Document)
            .options(
                selectinload(Document.source),
                selectinload(Document.versions),
                selectinload(Document.attachments),
                selectinload(Document.reviews),
                selectinload(Document.metadata_corrections),
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

    async def list_attachment_processing_batch(
        self,
        *,
        limit: int,
        attachment_ids: builtins.list[int] | None = None,
        eligible_only: bool = False,
    ) -> builtins.list[Attachment]:
        query = select(Attachment).order_by(Attachment.id).limit(limit)
        if attachment_ids is not None:
            query = query.where(Attachment.id.in_(attachment_ids))
        if eligible_only:
            query = query.where(
                or_(
                    Attachment.parse_status == "pending",
                    Attachment.retryable.is_(True),
                    and_(
                        Attachment.download_error_code == "DOWNLOAD_SSRF_BLOCKED",
                        Attachment.processed_at.is_(None),
                    ),
                    and_(
                        Attachment.requires_ocr.is_(True),
                        Attachment.processed_at.is_(None),
                    ),
                )
            )
        result = await self.session.scalars(query)
        return builtins.list(result.all())

    async def list_pending_attachments(
        self, *, limit: int = 1000, include_incomplete_audit: bool = False
    ) -> builtins.list[Attachment]:
        predicate = Attachment.parse_status == "pending"
        if include_incomplete_audit:
            predicate = or_(
                predicate,
                Attachment.file_type.is_(None),
                Attachment.parse_attempted_at.is_(None),
                (
                    Attachment.parse_status.in_(("failed", "unsupported"))
                    & Attachment.error_code.is_(None)
                ),
            )
        result = await self.session.scalars(
            select(Attachment).where(predicate).order_by(Attachment.id).limit(limit)
        )
        return builtins.list(result.all())

    async def list_pending_documents(self, *, limit: int = 1000) -> builtins.list[Document]:
        result = await self.session.scalars(
            select(Document)
            .where(Document.final_status.in_(("pending", "pending_manual_review", "pending_llm")))
            .options(selectinload(Document.attachments))
            .order_by(Document.id)
            .limit(limit)
        )
        return builtins.list(result.all())

    async def list_invalid_region_documents(self, *, limit: int = 1000) -> builtins.list[Document]:
        result = await self.session.scalars(
            select(Document).where(Document.region == "??").order_by(Document.id).limit(limit)
        )
        return builtins.list(result.all())

    async def has_review(self, document_id: int, review_type: str) -> bool:
        review_id = await self.session.scalar(
            select(DocumentReview.id)
            .where(
                DocumentReview.document_id == document_id,
                DocumentReview.review_type == review_type,
            )
            .limit(1)
        )
        return review_id is not None

    async def has_data_debt_review(self, document_id: int) -> bool:
        return await self.has_review(document_id, "data_debt_audit")

    async def add_review(self, review: DocumentReview) -> DocumentReview:
        self.session.add(review)
        await self.session.flush()
        return review

    async def add_metadata_correction_if_absent(
        self, correction: DocumentMetadataCorrection
    ) -> bool:
        existing = await self.session.scalar(
            select(DocumentMetadataCorrection.id).where(
                DocumentMetadataCorrection.correction_key == correction.correction_key
            )
        )
        if existing is not None:
            return False
        self.session.add(correction)
        await self.session.flush()
        return True

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
