from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.deduplication import content_hash
from app.models import DataLineage, Document, DocumentVersion, Source, SourceColumn
from app.parsers import ParsedArtifact
from app.repositories.documents import DocumentRepository
from app.services.versioning import VersioningService


async def test_parsed_update_creates_versions_marks_stale_and_records_lineage(app) -> None:
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key="versioning-source",
            name="Versioning source",
            domain="version.gov",
            homepage_url="https://version.gov/",
        )
        source_column = SourceColumn(
            source=source,
            column_key="policies",
            column_name="Policies",
            column_url="https://version.gov/list",
            request_interval_seconds=0,
        )
        document = Document(
            document_id=str(uuid.uuid4()),
            source=source,
            source_column=source_column,
            title="Original title",
            source_url="https://version.gov/policy/1",
            canonical_url="https://version.gov/policy/1",
            content="Original body",
            raw_content="<article><p>Original body</p></article>",
            content_hash=content_hash("Original body"),
            word_count=len("Original body"),
            version=1,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        service = VersioningService(DocumentRepository(session))
        result = await service.apply_parsed_update(
            document.id,
            ParsedArtifact(text="Updated body"),
            metadata_updates={"title": "Updated title"},
        )
        assert result.changed
        assert result.version == 2
        assert set(result.changed_fields) == {"content", "title"}
        refreshed = await session.get(Document, document.id)
        assert refreshed is not None
        assert refreshed.index_status == "stale"
        assert refreshed.title == "Updated title"
        version_count = await session.scalar(
            select(func.count())
            .select_from(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
        )
        lineage_count = await session.scalar(
            select(func.count())
            .select_from(DataLineage)
            .where(DataLineage.document_id == document.id)
        )
        assert version_count == 2
        assert lineage_count == 1
        unchanged = await service.apply_parsed_update(
            document.id,
            ParsedArtifact(text="Updated body"),
            metadata_updates={"title": "Updated title"},
        )
        assert not unchanged.changed
        assert unchanged.version == 2
