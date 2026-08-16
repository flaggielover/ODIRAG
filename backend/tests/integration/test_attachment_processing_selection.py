from __future__ import annotations

from datetime import UTC, datetime

from app.models import Attachment, Document
from app.repositories.documents import DocumentRepository


async def test_attachment_batch_selects_only_current_eligible_rows(app) -> None:
    async with app.state.database.session_factory() as session:
        document = Document(
            document_id="ATTACHMENT-BATCH-SELECTION",
            title="Attachment batch selection",
            source_url="https://example.gov/selection",
            content="selection fixture",
            word_count=17,
            final_status="pending",
            manual_review_status="pending",
        )
        session.add(document)
        await session.flush()
        rows = [
            Attachment(
                document_id=document.id,
                attachment_name="pending.pdf",
                source_url="https://example.gov/pending.pdf",
                parse_status="pending",
            ),
            Attachment(
                document_id=document.id,
                attachment_name="retry.pdf",
                source_url="https://example.gov/retry.pdf",
                parse_status="failed",
                error_code="DOWNLOAD_TIMEOUT",
                retryable=True,
            ),
            Attachment(
                document_id=document.id,
                attachment_name="historical.pdf",
                source_url="https://example.gov/historical.pdf",
                parse_status="failed",
                download_error_code="DOWNLOAD_SSRF_BLOCKED",
            ),
            Attachment(
                document_id=document.id,
                attachment_name="revalidated.pdf",
                source_url="https://example.gov/revalidated.pdf",
                parse_status="failed",
                download_error_code="DOWNLOAD_SSRF_BLOCKED",
                processed_at=datetime.now(UTC),
            ),
            Attachment(
                document_id=document.id,
                attachment_name="scan.jpg",
                source_url="https://example.gov/scan.jpg",
                parse_status="failed",
                requires_ocr=True,
            ),
            Attachment(
                document_id=document.id,
                attachment_name="legacy.doc",
                source_url="https://example.gov/legacy.doc",
                parse_status="unsupported",
                error_code="UNSUPPORTED_LEGACY_FORMAT",
            ),
        ]
        session.add_all(rows)
        await session.commit()

        selected = await DocumentRepository(session).list_attachment_processing_batch(
            limit=100,
            eligible_only=True,
        )

        selected_names = {attachment.attachment_name for attachment in selected}
        assert selected_names == {
            "pending.pdf",
            "retry.pdf",
            "historical.pdf",
            "scan.jpg",
        }


async def test_attachment_batch_accepts_an_explicit_sample(app) -> None:
    async with app.state.database.session_factory() as session:
        document = Document(
            document_id="ATTACHMENT-EXPLICIT-SELECTION",
            title="Attachment explicit selection",
            source_url="https://example.gov/explicit-selection",
            content="selection fixture",
            word_count=17,
            final_status="pending",
            manual_review_status="pending",
        )
        session.add(document)
        await session.flush()
        first = Attachment(
            document_id=document.id,
            attachment_name="first.doc",
            source_url="https://example.gov/first.doc",
            parse_status="unsupported",
        )
        second = Attachment(
            document_id=document.id,
            attachment_name="second.pdf",
            source_url="https://example.gov/second.pdf",
            parse_status="parsed",
        )
        session.add_all([first, second])
        await session.commit()

        selected = await DocumentRepository(session).list_attachment_processing_batch(
            limit=10,
            attachment_ids=[second.id, first.id],
        )

        assert [attachment.id for attachment in selected] == sorted([first.id, second.id])
