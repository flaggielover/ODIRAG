from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import anyio

from app.cleaners import clean_text
from app.errors import NotFoundError
from app.models import Attachment
from app.parsers import ParsedArtifact, ParserRegistry
from app.repositories.documents import DocumentRepository
from app.services.versioning import VersioningResult, VersioningService


@dataclass(frozen=True, slots=True)
class AttachmentAuditSummary:
    attempted: int
    parsed: int
    unsupported: int
    failed: int
    ocr_success: int
    ocr_partial: int
    ocr_failed: int


class ParsingService:
    def __init__(
        self,
        repository: DocumentRepository,
        registry: ParserRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry or ParserRegistry()
        self.versioning = VersioningService(repository)

    async def parse_attachment(self, attachment_id: int, *, force: bool = False) -> ParsedArtifact:
        attachment = await self.repository.get_attachment(attachment_id)
        if attachment is None:
            raise NotFoundError("Attachment", attachment_id)
        filename = _filename(attachment)
        attachment.file_type = _file_type(filename, attachment.mime_type)
        if not force and attachment.parse_status == "parsed" and attachment.parsed_text is not None:
            return ParsedArtifact(
                text=attachment.parsed_text,
                metadata={"parser": attachment.parser or "unknown"},
            )
        attachment.parse_attempted_at = datetime.now(UTC)
        if attachment.parsed_text and attachment.parsed_text.strip() and not attachment.local_path:
            attachment.parsed_text = clean_text(attachment.parsed_text)
            attachment.extracted_text_length = len(attachment.parsed_text)
            attachment.parser = attachment.parser or "upstream_extracted_text"
            if attachment.requires_ocr:
                attachment.ocr_status = "failed"
                attachment.ocr_provider = None
                self._mark_failure(
                    attachment,
                    status="failed",
                    error_code="OCR_UNAVAILABLE",
                    retryable=False,
                    message="attachment requires OCR but no OCR provider is configured",
                )
                await self.repository.commit()
                raise ValueError("attachment requires OCR but no OCR provider is configured")
            attachment.parse_status = "parsed"
            attachment.ocr_status = "not_required"
            attachment.error_code = None
            attachment.retryable = False
            attachment.error_message = None
            await self.repository.commit()
            return ParsedArtifact(
                text=attachment.parsed_text,
                requires_ocr=attachment.requires_ocr,
                metadata={"parser": attachment.parser},
            )
        if _requires_ocr_file(filename, attachment.mime_type):
            attachment.requires_ocr = True
            attachment.ocr_status = "failed"
            attachment.ocr_provider = None
            self._mark_failure(
                attachment,
                status="failed",
                error_code="OCR_UNAVAILABLE",
                retryable=False,
                message="image attachment requires OCR but no OCR provider is configured",
            )
            await self.repository.commit()
            raise ValueError("attachment requires OCR but no OCR provider is configured")
        if not Path(filename).suffix:
            self._mark_failure(
                attachment,
                status="failed",
                error_code="FILE_TYPE_UNKNOWN",
                retryable=True,
                message="attachment file type cannot be determined",
            )
            await self.repository.commit()
            raise ValueError("attachment file type cannot be determined")
        try:
            parser = self.registry.get(filename)
        except ValueError:
            self._mark_failure(
                attachment,
                status="unsupported",
                error_code="UNSUPPORTED_FILE_TYPE",
                retryable=False,
                message="no parser is registered for this file type",
            )
            await self.repository.commit()
            raise
        if not attachment.local_path:
            self._mark_failure(
                attachment,
                status="failed",
                error_code="ATTACHMENT_NOT_DOWNLOADED",
                retryable=True,
                message="attachment bytes are not available locally",
            )
            await self.repository.commit()
            raise ValueError("attachment has no downloaded local path")
        path = Path(attachment.local_path)
        if not await anyio.to_thread.run_sync(path.is_file):
            self._mark_failure(
                attachment,
                status="failed",
                error_code="ATTACHMENT_FILE_MISSING",
                retryable=True,
                message="downloaded attachment file is missing",
            )
            await self.repository.commit()
            raise FileNotFoundError(path)
        try:
            content = await anyio.to_thread.run_sync(path.read_bytes)
            parsed = parser.parse(content, filename=filename)
            attachment.parser = parser.__class__.__name__
            attachment.parsed_text = (
                "\f".join(clean_text(page) for page in parsed.pages)
                if parsed.pages
                else clean_text(parsed.text)
            )
            attachment.extracted_text_length = len(attachment.parsed_text or "")
            attachment.page_count = len(parsed.pages) or parsed.metadata.get("page_count")
            attachment.requires_ocr = parsed.requires_ocr
            if parsed.requires_ocr:
                attachment.ocr_status = "failed"
                attachment.ocr_provider = None
                self._mark_failure(
                    attachment,
                    status="failed",
                    error_code="OCR_UNAVAILABLE",
                    retryable=False,
                    message="attachment requires OCR but no OCR provider is configured",
                )
                await self.repository.commit()
                raise ValueError("attachment requires OCR but no OCR provider is configured")
            if not attachment.parsed_text:
                self._mark_failure(
                    attachment,
                    status="failed",
                    error_code="NO_TEXT_EXTRACTED",
                    retryable=False,
                    message="attachment parser produced no text",
                )
                await self.repository.commit()
                raise ValueError("attachment parser produced no text")
            attachment.parse_status = "parsed"
            attachment.ocr_status = "not_required"
            attachment.ocr_provider = None
            attachment.error_code = None
            attachment.retryable = False
            attachment.error_message = None
            await self.repository.commit()
            return parsed
        except Exception:
            if attachment.error_code is None:
                self._mark_failure(
                    attachment,
                    status="failed",
                    error_code="PARSE_ERROR",
                    retryable=False,
                    message="attachment parser failed",
                )
            await self.repository.commit()
            raise

    async def audit_pending_attachments(self, *, limit: int = 1000) -> AttachmentAuditSummary:
        """Parse a bounded batch and persist an outcome for every attempted attachment."""

        attachments = await self.repository.list_pending_attachments(limit=limit)
        counts = {
            "parsed": 0,
            "unsupported": 0,
            "failed": 0,
            "ocr_success": 0,
            "ocr_partial": 0,
            "ocr_failed": 0,
        }
        for attachment in attachments:
            try:
                await self.parse_attachment(attachment.id)
            except Exception:
                await self.repository.session.refresh(attachment)
            if attachment.parse_status == "parsed":
                counts["parsed"] += 1
            elif attachment.parse_status == "unsupported":
                counts["unsupported"] += 1
            else:
                counts["failed"] += 1
            if attachment.ocr_status in {"success", "partial", "failed"}:
                counts[f"ocr_{attachment.ocr_status}"] += 1
        return AttachmentAuditSummary(
            attempted=len(attachments),
            parsed=counts["parsed"],
            unsupported=counts["unsupported"],
            failed=counts["failed"],
            ocr_success=counts["ocr_success"],
            ocr_partial=counts["ocr_partial"],
            ocr_failed=counts["ocr_failed"],
        )

    async def reparse_html_document(
        self, document_id: int, *, crawl_task_id: int | None = None
    ) -> VersioningResult:
        document = await self.repository.get(document_id)
        if document is None:
            raise NotFoundError("Document", document_id)
        if not document.raw_content:
            raise ValueError("document has no raw HTML content")
        parsed = self.registry.parse("document.html", document.raw_content.encode("utf-8"))
        return await self.versioning.apply_parsed_update(
            document.id, parsed, crawl_task_id=crawl_task_id
        )

    @staticmethod
    def _mark_failure(
        attachment: Attachment,
        *,
        status: str,
        error_code: str,
        retryable: bool,
        message: str,
    ) -> None:
        attachment.parse_status = status
        attachment.error_code = error_code
        attachment.retryable = retryable
        attachment.error_message = message


def _filename(attachment: Attachment) -> str:
    for candidate in (
        attachment.local_path,
        urlsplit(attachment.source_url).path,
        attachment.attachment_name,
    ):
        if candidate and _safe_suffix(candidate):
            return Path(candidate).name
    extension = (attachment.file_extension or "").strip()
    if extension:
        return f"attachment.{extension.lstrip('.')}"
    return "attachment"


def _file_type(filename: str, mime_type: str | None) -> str:
    extension = _safe_suffix(filename).lstrip(".")
    if extension:
        return extension
    if mime_type:
        return mime_type.split("/", 1)[-1].lower()
    return "unknown"


def _requires_ocr_file(filename: str, mime_type: str | None) -> bool:
    if mime_type and mime_type.lower().startswith("image/"):
        return True
    return _safe_suffix(filename) in {
        ".bmp",
        ".gif",
        ".jpeg",
        ".jpg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
    }


def _safe_suffix(value: str) -> str:
    suffix = Path(value).suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ""
