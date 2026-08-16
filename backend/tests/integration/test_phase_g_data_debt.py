from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import (
    Attachment,
    Document,
    DocumentMetadataCorrection,
    DocumentReview,
)
from app.ocr import OcrResult
from app.parsers import ParsedArtifact, ParserRegistry
from app.repositories.documents import DocumentRepository
from app.services.data_quality import DataDebtCleanupService
from app.services.parsing import ParsingService


async def _document(
    session,
    suffix: str,
    *,
    region: str | None = "Sichuan",
    final_status: str = "pending",
) -> Document:
    document = Document(
        document_id=f"PHASE-G-{suffix}",
        title=f"Phase G {suffix}",
        source_url=f"https://example.gov/policies/{suffix}",
        content="Policy content",
        word_count=14,
        region=region,
        final_status=final_status,
        manual_review_status="pending",
    )
    session.add(document)
    await session.flush()
    return document


async def test_attachment_parser_records_parsed_audit_fields(app) -> None:
    path = Path(__file__).parents[3] / "config" / "prompts" / "document_review_v1.txt"
    async with app.state.database.session_factory() as session:
        document = await _document(session, "parsed")
        attachment = Attachment(
            document_id=document.id,
            attachment_name="policy.txt",
            source_url="https://example.gov/files/policy.txt",
            local_path=str(path),
            download_status="completed",
        )
        session.add(attachment)
        await session.commit()
        await session.refresh(attachment)

        result = await ParsingService(DocumentRepository(session)).parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert result.text.strip()
        assert attachment.parse_status == "parsed"
        assert attachment.file_type == "txt"
        assert attachment.parser == "TextParser"
        assert attachment.extracted_text_length == len(attachment.parsed_text or "")
        assert attachment.ocr_status == "not_required"
        assert attachment.error_code is None
        assert attachment.retryable is False
        assert attachment.parse_attempted_at is not None


async def test_attachment_parser_records_unsupported_and_missing_bytes(app) -> None:
    unsupported_path = Path(__file__).with_suffix(".exe")
    async with app.state.database.session_factory() as session:
        document = await _document(session, "terminal-failures")
        unsupported = Attachment(
            document_id=document.id,
            attachment_name="policy.exe",
            source_url="https://example.gov/files/policy.exe",
            local_path=str(unsupported_path),
            download_status="completed",
        )
        missing = Attachment(
            document_id=document.id,
            attachment_name="policy.pdf",
            source_url="https://example.gov/files/policy.pdf",
            download_status="completed",
        )
        session.add_all([unsupported, missing])
        await session.commit()

        summary = await ParsingService(DocumentRepository(session)).audit_pending_attachments()
        await session.refresh(unsupported)
        await session.refresh(missing)

        assert summary.attempted == 2
        assert summary.unsupported == 1
        assert summary.failed == 1
        assert unsupported.parse_status == "unsupported"
        assert unsupported.error_code == "UNSUPPORTED_FILE_TYPE"
        assert unsupported.retryable is False
        assert missing.parse_status == "failed"
        assert missing.error_code == "ATTACHMENT_NOT_DOWNLOADED"
        assert missing.retryable is True


async def test_image_attachment_records_ocr_unavailable_before_download(app) -> None:
    async with app.state.database.session_factory() as session:
        document = await _document(session, "image-ocr")
        attachment = Attachment(
            document_id=document.id,
            attachment_name="notice.png",
            source_url="https://example.gov/files/notice.png",
            mime_type="image/png",
            download_status="completed",
        )
        session.add(attachment)
        await session.commit()
        await session.refresh(attachment)

        with pytest.raises(ValueError, match="downloaded local path"):
            await ParsingService(DocumentRepository(session)).parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert attachment.parse_status == "failed"
        assert attachment.error_code == "ATTACHMENT_NOT_DOWNLOADED"
        assert attachment.ocr_status == "not_required"
        assert attachment.retryable is True


async def test_bulk_audit_counts_ocr_failure(app) -> None:
    async with app.state.database.session_factory() as session:
        document = await _document(session, "bulk-image-ocr")
        session.add(
            Attachment(
                document_id=document.id,
                attachment_name="scan.jpg",
                source_url="https://example.gov/files/scan.jpg",
                mime_type="image/jpeg",
                download_status="completed",
            )
        )
        await session.commit()

        summary = await ParsingService(DocumentRepository(session)).audit_pending_attachments()

        assert summary.attempted == 1
        assert summary.failed == 1
        assert summary.ocr_failed == 0
        assert summary.ocr_success == 0
        assert summary.ocr_partial == 0


class _OcrRequiredParser:
    version = "fixture-v1"

    def parse(self, content: bytes, *, filename: str | None = None) -> ParsedArtifact:
        del content, filename
        return ParsedArtifact(text="", pages=("",), requires_ocr=True)


class _FailingOcrProvider:
    name = "fixture-failing-ocr"
    version = "fixture-v1"

    async def recognize(self, content: bytes, *, file_type: str, filename: str) -> OcrResult:
        del content, file_type, filename
        raise RuntimeError("fixture provider failure")


class _FixtureOcrProvider:
    name = "fixture-ocr"
    version = "fixture-v1"

    async def recognize(
        self,
        content: bytes,
        *,
        file_type: str,
        filename: str,
    ) -> OcrResult:
        assert content
        assert file_type in {"jpg", "pdf"}
        assert filename
        return OcrResult(
            text="OCR extracted policy text",
            pages=("OCR extracted policy text",),
            provider=self.name,
        )


async def test_image_attachment_uses_injected_ocr_and_records_provenance(app) -> None:
    path = Path(__file__).parents[3] / "config" / "prompts" / "document_review_v1.txt"
    async with app.state.database.session_factory() as session:
        document = await _document(session, "image-ocr-success")
        attachment = Attachment(
            document_id=document.id,
            attachment_name="notice.jpg",
            source_url="https://example.gov/files/notice.jpg",
            local_path=str(path),
            mime_type="image/jpeg",
            file_type="jpg",
            download_status="completed",
        )
        session.add(attachment)
        await session.commit()

        result = await ParsingService(
            DocumentRepository(session), ocr_provider=_FixtureOcrProvider()
        ).parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert result.text == "OCR extracted policy text"
        assert attachment.parse_status == "parsed"
        assert attachment.ocr_status == "success"
        assert attachment.ocr_provider == "fixture-ocr"
        assert attachment.extraction_method == "image_ocr"
        assert attachment.requires_ocr is False
        assert attachment.error_code is None


async def test_ocr_required_attachment_is_honestly_failed_when_provider_missing(app) -> None:
    path = Path(__file__).parents[3] / "config" / "prompts" / "document_review_v1.txt"
    registry = ParserRegistry({".txt": _OcrRequiredParser()})
    async with app.state.database.session_factory() as session:
        document = await _document(session, "ocr")
        attachment = Attachment(
            document_id=document.id,
            attachment_name="scan.txt",
            source_url="https://example.gov/files/scan.txt",
            local_path=str(path),
            download_status="completed",
        )
        session.add(attachment)
        await session.commit()
        await session.refresh(attachment)

        with pytest.raises(ValueError, match="requires OCR"):
            await ParsingService(DocumentRepository(session), registry).parse_attachment(
                attachment.id
            )
        await session.refresh(attachment)

        assert attachment.parse_status == "failed"
        assert attachment.requires_ocr is True
        assert attachment.ocr_status == "failed"
        assert attachment.error_code == "OCR_PROVIDER_UNAVAILABLE"
        assert attachment.retryable is False


async def test_ocr_provider_failure_has_explicit_retryable_terminal_state(app) -> None:
    path = Path(__file__).parent / ".ocr-fixture-failure.jpg"
    path.write_bytes(b"\xff\xd8\xfffixture")
    try:
        async with app.state.database.session_factory() as session:
            document = await _document(session, "image-ocr-failure")
            attachment = Attachment(
                document_id=document.id,
                attachment_name="scan.jpg",
                source_url="https://example.gov/files/scan.jpg",
                local_path=str(path),
                mime_type="image/jpeg",
                download_status="completed",
            )
            session.add(attachment)
            await session.commit()

            with pytest.raises(RuntimeError, match="fixture provider failure"):
                await ParsingService(
                    DocumentRepository(session), ocr_provider=_FailingOcrProvider()
                ).parse_attachment(attachment.id)
            await session.refresh(attachment)

            assert attachment.parse_status == "failed"
            assert attachment.error_code == "OCR_FAILED"
            assert attachment.retryable is True
            assert attachment.ocr_status == "failed"
    finally:
        path.unlink(missing_ok=True)


async def test_data_debt_cleanup_is_idempotent_and_preserves_manual_gate(app) -> None:
    async with app.state.database.session_factory() as session:
        document = await _document(session, "audit", region="??")
        document_id = document.id
        attachment = Attachment(
            document_id=document.id,
            attachment_name="upstream.txt",
            source_url="https://example.gov/files/upstream.txt",
            download_status="completed",
            parsed_text="Already extracted upstream",
        )
        session.add(attachment)
        await session.commit()

        service = DataDebtCleanupService(DocumentRepository(session))
        first = await service.run()
        second = await service.run()
        await session.refresh(document)
        await session.refresh(attachment)

        reviews = await session.scalar(
            select(func.count(DocumentReview.id)).where(
                DocumentReview.document_id == document_id,
                DocumentReview.review_type == "data_debt_audit",
            )
        )
        corrections = await session.scalar(
            select(func.count(DocumentMetadataCorrection.id)).where(
                DocumentMetadataCorrection.document_id == document_id
            )
        )

        assert first.attachments.parsed == 1
        assert second.attachments.attempted == 0
        assert first.human_review_required == 1
        assert second.human_review_required == 0
        assert reviews == 1
        assert corrections == 1
        assert document.final_status == "pending"
        assert document.manual_review_status == "pending"
        assert document.region == "??"
        assert attachment.parse_status == "parsed"
        assert attachment.parser == "upstream_extracted_text"


async def test_data_debt_cleanup_auto_rejects_only_deterministic_empty_document(app) -> None:
    async with app.state.database.session_factory() as session:
        empty = await _document(session, "empty-hard-reject")
        empty.content = ""
        empty.word_count = 0
        await session.commit()

        result = await DataDebtCleanupService(DocumentRepository(session)).run()
        await session.refresh(empty)

        assert result.auto_rejected == 1
        assert empty.final_status == "rejected"
        assert empty.manual_review_status == "not_required"
        review = await session.scalar(
            select(DocumentReview).where(
                DocumentReview.document_id == empty.id,
                DocumentReview.review_type == "data_debt_hard_reject",
            )
        )
        assert review is not None
        assert review.decision == "reject"
        assert "content_too_short_hard" in review.reasons_json


async def test_data_debt_cleanup_does_not_review_approved_documents(app) -> None:
    async with app.state.database.session_factory() as session:
        document = await _document(session, "approved", final_status="approved")
        document.manual_review_status = "approved"
        await session.commit()

        summary = await DataDebtCleanupService(DocumentRepository(session)).run()
        reviews = await session.scalar(
            select(func.count(DocumentReview.id)).where(
                DocumentReview.document_id == document.id,
                DocumentReview.review_type == "data_debt_audit",
            )
        )

        assert summary.pending_documents_audited == 0
        assert summary.human_review_required == 0
        assert reviews == 0
