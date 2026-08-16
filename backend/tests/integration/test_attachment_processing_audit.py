from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from app.models import Attachment, Document
from app.ocr import OcrResult
from app.parsers import ParsedArtifact, ParserRegistry
from app.repositories.documents import DocumentRepository
from app.services.parsing import ParsingService


@pytest.fixture
def processing_root() -> Iterator[Path]:
    parent = Path(".test-data") / "attachment-processing-audit"
    parent.mkdir(parents=True, exist_ok=True)
    root = parent / f"case-{uuid4().hex}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root)


class _CountingParser:
    def __init__(self, *, version: str, text: str) -> None:
        self.version = version
        self.text = text
        self.calls = 0

    def parse(self, content: bytes, *, filename: str | None = None) -> ParsedArtifact:
        assert content
        assert filename
        self.calls += 1
        return ParsedArtifact(text=self.text)


class _CountingOcrProvider:
    name = "fixture-ocr"

    def __init__(self, *, version: str) -> None:
        self.version = version
        self.calls = 0

    async def recognize(
        self,
        content: bytes,
        *,
        file_type: str,
        filename: str,
    ) -> OcrResult:
        assert content
        assert file_type == "jpg"
        assert filename
        self.calls += 1
        text = f"OCR text from {self.version}"
        return OcrResult(
            text=text,
            pages=(text,),
            provider=self.name,
            version=self.version,
        )


async def _attachment(session, *, suffix: str, local_path: str, filename: str) -> Attachment:
    document = Document(
        document_id=f"ATTACHMENT-AUDIT-{suffix}",
        title=f"Attachment audit {suffix}",
        source_url=f"https://example.gov/policies/{suffix}",
        content="Policy content",
        word_count=14,
    )
    session.add(document)
    await session.flush()
    attachment = Attachment(
        document_id=document.id,
        attachment_name=filename,
        source_url=f"https://example.gov/files/{filename}",
        local_path=local_path,
        download_status="completed",
    )
    session.add(attachment)
    await session.commit()
    await session.refresh(attachment)
    return attachment


async def test_parser_cache_uses_file_bytes_and_parser_version(app, processing_root) -> None:
    path = processing_root / "policy.txt"
    path.write_bytes(b"first file bytes")
    async with app.state.database.session_factory() as session:
        attachment = await _attachment(
            session,
            suffix="parser-cache",
            local_path=str(path),
            filename=path.name,
        )
        parser_v1 = _CountingParser(version="v1", text="parsed v1")
        service_v1 = ParsingService(
            DocumentRepository(session),
            ParserRegistry({".txt": parser_v1}),
        )

        await service_v1.parse_attachment(attachment.id)
        await service_v1.parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert parser_v1.calls == 1
        assert attachment.file_hash == hashlib.sha256(b"first file bytes").hexdigest()
        assert attachment.parser == "_CountingParser"
        assert attachment.parser_version == "v1"
        assert attachment.processed_at is not None

        parser_v2 = _CountingParser(version="v2", text="parsed v2")
        service_v2 = ParsingService(
            DocumentRepository(session),
            ParserRegistry({".txt": parser_v2}),
        )
        await service_v2.parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert parser_v2.calls == 1
        assert attachment.parser_version == "v2"
        assert attachment.parsed_text == "parsed v2"

        path.write_bytes(b"second file bytes")
        await service_v2.parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert parser_v2.calls == 2
        assert attachment.file_hash == hashlib.sha256(b"second file bytes").hexdigest()


async def test_ocr_cache_includes_provider_version_and_records_metrics(
    app, processing_root
) -> None:
    path = processing_root / "notice.jpg"
    path.write_bytes(b"actual image fixture bytes")
    async with app.state.database.session_factory() as session:
        attachment = await _attachment(
            session,
            suffix="ocr-cache",
            local_path=str(path),
            filename=path.name,
        )
        provider_v1 = _CountingOcrProvider(version="v1")
        service_v1 = ParsingService(DocumentRepository(session), ocr_provider=provider_v1)

        await service_v1.parse_attachment(attachment.id)
        await service_v1.parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert provider_v1.calls == 1
        assert attachment.parser == "ocr"
        assert attachment.parser_version == "ocr:1"
        assert attachment.ocr_provider == "fixture-ocr"
        assert attachment.ocr_version == "v1"
        assert attachment.ocr_page_count == 1
        assert attachment.ocr_text_length == len("OCR text from v1")
        assert attachment.ocr_latency_ms is not None

        provider_v2 = _CountingOcrProvider(version="v2")
        await ParsingService(
            DocumentRepository(session), ocr_provider=provider_v2
        ).parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert provider_v2.calls == 1
        assert attachment.ocr_version == "v2"
        assert attachment.parsed_text == "OCR text from v2"


async def test_missing_ocr_provider_uses_existing_failed_state(app, processing_root) -> None:
    path = processing_root / "scan.jpg"
    path.write_bytes(b"actual image fixture bytes")
    async with app.state.database.session_factory() as session:
        attachment = await _attachment(
            session,
            suffix="ocr-unavailable",
            local_path=str(path),
            filename=path.name,
        )

        with pytest.raises(ValueError, match="no OCR provider"):
            await ParsingService(DocumentRepository(session)).parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert attachment.parse_status == "failed"
        assert attachment.error_code == "OCR_PROVIDER_UNAVAILABLE"
        assert attachment.requires_ocr is True
        assert attachment.ocr_status == "failed"
        assert attachment.retryable is False
        assert attachment.ocr_page_count == 0
        assert attachment.ocr_text_length == 0
        assert attachment.ocr_latency_ms == 0
        assert attachment.processed_at is not None


async def test_parser_rejects_oversize_file_before_parser_call(app, processing_root) -> None:
    path = processing_root / "large.txt"
    path.write_bytes(b"four")
    async with app.state.database.session_factory() as session:
        attachment = await _attachment(
            session,
            suffix="oversize",
            local_path=str(path),
            filename=path.name,
        )
        parser = _CountingParser(version="v1", text="must not run")

        with pytest.raises(ValueError, match="parser size limit"):
            await ParsingService(
                DocumentRepository(session),
                ParserRegistry({".txt": parser}),
                max_file_bytes=3,
            ).parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert parser.calls == 0
        assert attachment.parse_status == "failed"
        assert attachment.error_code == "ATTACHMENT_TOO_LARGE"
        assert attachment.retryable is False
        assert attachment.processed_at is not None


async def test_local_legacy_magic_is_not_reported_as_docx_parse_failure(
    app, processing_root
) -> None:
    path = processing_root / "incorrect-modern-extension.docx"
    content = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1legacy-office"
    path.write_bytes(content)
    async with app.state.database.session_factory() as session:
        attachment = await _attachment(
            session,
            suffix="legacy-magic",
            local_path=str(path),
            filename=path.name,
        )
        attachment.mime_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        await session.commit()

        with pytest.raises(ValueError, match="legacy Office"):
            await ParsingService(DocumentRepository(session)).parse_attachment(attachment.id)
        await session.refresh(attachment)

        assert attachment.download_status == "completed"
        assert attachment.parse_status == "unsupported"
        assert attachment.file_type == "legacy_office"
        assert attachment.file_hash == hashlib.sha256(content).hexdigest()
        assert attachment.type_detection_source == "magic"
        assert attachment.error_code == "UNSUPPORTED_LEGACY_FORMAT"
        assert attachment.retryable is False
