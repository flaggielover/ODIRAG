from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.cleaners import clean_text
from app.deduplication import content_hash, simhash
from app.errors import NotFoundError
from app.models import DataLineage, Document, DocumentVersion
from app.parsers import ParsedArtifact
from app.repositories.documents import DocumentRepository


@dataclass(frozen=True, slots=True)
class VersioningResult:
    changed: bool
    version: int
    changed_fields: tuple[str, ...]
    document_version_id: int | None = None
    lineage_id: str | None = None


class VersioningService:
    def __init__(self, repository: DocumentRepository) -> None:
        self.repository = repository

    async def apply_parsed_update(
        self,
        document_id: int,
        parsed: ParsedArtifact,
        *,
        metadata_updates: dict[str, Any] | None = None,
        crawl_task_id: int | None = None,
        attachment_id: int | None = None,
    ) -> VersioningResult:
        document = await self.repository.get(document_id)
        if document is None:
            raise NotFoundError("Document", document_id)
        new_content = clean_text(parsed.text)
        new_hash = content_hash(new_content)
        if document.content_hash == new_hash:
            return VersioningResult(False, document.version, ())
        changes = self._changed_fields(document, new_content, metadata_updates or {})
        try:
            if await self.repository.version_count(document.id) == 0:
                await self.repository.add_version(self._snapshot(document, ()))
            document.version += 1
            document.content = new_content
            document.content_hash = new_hash
            document.simhash = f"{simhash(new_content):016x}"
            document.word_count = len(new_content)
            document.index_status = "stale"
            for field_name, value in (metadata_updates or {}).items():
                if field_name in _UPDATABLE_METADATA_FIELDS:
                    setattr(document, field_name, value)
            version = await self.repository.add_version(self._snapshot(document, changes))
            lineage_identifier = str(uuid.uuid4())
            await self.repository.add_lineage(
                DataLineage(
                    lineage_id=lineage_identifier,
                    source_id=document.source_id,
                    crawl_task_id=crawl_task_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    attachment_id=attachment_id,
                )
            )
            await self.repository.commit()
            return VersioningResult(
                True,
                document.version,
                tuple(changes),
                version.id,
                lineage_identifier,
            )
        except Exception:
            await self.repository.rollback()
            raise

    async def apply_metadata_update(
        self, document_id: int, metadata_updates: dict[str, Any]
    ) -> VersioningResult:
        """Persist an operator edit as a new immutable document version."""
        document = await self.repository.get(document_id)
        if document is None:
            raise NotFoundError("Document", document_id)
        updates = {
            field_name: value
            for field_name, value in metadata_updates.items()
            if field_name in _UPDATABLE_METADATA_FIELDS and getattr(document, field_name) != value
        }
        if not updates:
            return VersioningResult(False, document.version, ())
        try:
            if await self.repository.version_count(document.id) == 0:
                await self.repository.add_version(self._snapshot(document, ()))
            document.version += 1
            document.index_status = "stale"
            for field_name, value in updates.items():
                setattr(document, field_name, value)
            version = await self.repository.add_version(self._snapshot(document, tuple(updates)))
            lineage_identifier = str(uuid.uuid4())
            await self.repository.add_lineage(
                DataLineage(
                    lineage_id=lineage_identifier,
                    source_id=document.source_id,
                    document_id=document.id,
                    document_version_id=version.id,
                )
            )
            await self.repository.commit()
            return VersioningResult(
                True,
                document.version,
                tuple(updates),
                version.id,
                lineage_identifier,
            )
        except Exception:
            await self.repository.rollback()
            raise

    @staticmethod
    def _snapshot(
        document: Document, changed_fields: tuple[str, ...] | list[str]
    ) -> DocumentVersion:
        return DocumentVersion(
            document_id=document.id,
            version=document.version,
            content_hash=document.content_hash or content_hash(document.content),
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
            changed_fields_json=list(changed_fields),
        )

    @staticmethod
    def _changed_fields(
        document: Document, new_content: str, metadata_updates: dict[str, Any]
    ) -> list[str]:
        fields = []
        if document.content != new_content:
            fields.append("content")
        for field_name, value in metadata_updates.items():
            if field_name in _UPDATABLE_METADATA_FIELDS and getattr(document, field_name) != value:
                fields.append(field_name)
        return fields


_UPDATABLE_METADATA_FIELDS = {
    "title",
    "subtitle",
    "publish_date",
    "author",
    "issuing_authority",
    "document_number",
    "region",
    "city",
    "document_type",
    "language",
}
