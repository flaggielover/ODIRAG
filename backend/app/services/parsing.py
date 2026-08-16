from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

import anyio

from app.attachments import detect_attachment_type
from app.cleaners import clean_text
from app.errors import NotFoundError
from app.models import Attachment
from app.ocr import OcrProvider
from app.parsers import ParsedArtifact, Parser, ParserRegistry
from app.repositories.documents import DocumentRepository
from app.services.versioning import VersioningResult, VersioningService

_DEFAULT_MAX_PARSE_BYTES = 50 * 1024 * 1024
_UPSTREAM_PARSER_VERSION = "1"
_OCR_PIPELINE_VERSION = "1"


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
        ocr_provider: OcrProvider | None = None,
        max_file_bytes: int = _DEFAULT_MAX_PARSE_BYTES,
    ) -> None:
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        self.repository = repository
        self.registry = registry or ParserRegistry()
        self.ocr_provider = ocr_provider
        self.max_file_bytes = max_file_bytes
        self.versioning = VersioningService(repository)

    async def parse_attachment(self, attachment_id: int, *, force: bool = False) -> ParsedArtifact:
        attachment = await self.repository.get_attachment(attachment_id)
        if attachment is None:
            raise NotFoundError("Attachment", attachment_id)
        filename = _filename(attachment)
        attachment.file_type = _file_type(filename, attachment.mime_type)
        if attachment.parsed_text and attachment.parsed_text.strip() and not attachment.local_path:
            if (
                not force
                and attachment.parse_status == "parsed"
                and attachment.parser == "upstream_extracted_text"
                and attachment.parser_version == _UPSTREAM_PARSER_VERSION
                and not attachment.requires_ocr
            ):
                return ParsedArtifact(
                    text=attachment.parsed_text,
                    metadata={
                        "parser": attachment.parser,
                        "parser_version": attachment.parser_version,
                    },
                )
            attachment.parse_attempted_at = datetime.now(UTC)
            attachment.parsed_text = clean_text(attachment.parsed_text)
            attachment.extracted_text_length = len(attachment.parsed_text)
            attachment.parser = "upstream_extracted_text"
            attachment.parser_version = _UPSTREAM_PARSER_VERSION
            attachment.extraction_method = attachment.extraction_method or "upstream_extracted_text"
            if attachment.requires_ocr:
                attachment.ocr_status = "failed"
                attachment.ocr_provider = None
                attachment.ocr_version = None
                attachment.ocr_page_count = 0
                attachment.ocr_text_length = 0
                attachment.ocr_latency_ms = 0
                self._mark_failure(
                    attachment,
                    status="failed",
                    error_code="OCR_PROVIDER_UNAVAILABLE",
                    retryable=False,
                    message="attachment requires OCR but no OCR provider is configured",
                )
                await self.repository.commit()
                raise ValueError("attachment requires OCR but no OCR provider is configured")
            attachment.parse_status = "parsed"
            _reset_ocr_audit(attachment)
            attachment.error_code = None
            attachment.retryable = False
            attachment.error_message = None
            attachment.processed_at = datetime.now(UTC)
            await self.repository.commit()
            return ParsedArtifact(
                text=attachment.parsed_text,
                requires_ocr=attachment.requires_ocr,
                metadata={
                    "parser": attachment.parser,
                    "parser_version": attachment.parser_version,
                },
            )
        if not Path(filename).suffix:
            attachment.parse_attempted_at = datetime.now(UTC)
            self._mark_failure(
                attachment,
                status="failed",
                error_code="FILE_TYPE_UNKNOWN",
                retryable=True,
                message="attachment file type cannot be determined",
            )
            await self.repository.commit()
            raise ValueError("attachment file type cannot be determined")
        requires_ocr_file = _requires_ocr_file(filename, attachment.mime_type)
        parser = None
        if not requires_ocr_file:
            try:
                parser = self.registry.get(filename)
            except ValueError:
                attachment.parse_attempted_at = datetime.now(UTC)
                error_code = (
                    "UNSUPPORTED_LEGACY_FORMAT"
                    if _safe_suffix(filename) in {".doc", ".xls"}
                    else "UNSUPPORTED_FILE_TYPE"
                )
                self._mark_failure(
                    attachment,
                    status="unsupported",
                    error_code=error_code,
                    retryable=False,
                    message="no reliable parser is registered for this file type",
                )
                await self.repository.commit()
                raise
        if not attachment.local_path:
            attachment.parse_attempted_at = datetime.now(UTC)
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
            attachment.parse_attempted_at = datetime.now(UTC)
            self._mark_failure(
                attachment,
                status="failed",
                error_code="ATTACHMENT_FILE_MISSING",
                retryable=True,
                message="downloaded attachment file is missing",
            )
            await self.repository.commit()
            raise FileNotFoundError(path)
        attempt_started = False
        try:
            file_size = (await anyio.to_thread.run_sync(path.stat)).st_size
            if file_size > self.max_file_bytes:
                attempt_started = True
                attachment.parse_attempted_at = datetime.now(UTC)
                self._mark_failure(
                    attachment,
                    status="failed",
                    error_code="ATTACHMENT_TOO_LARGE",
                    retryable=False,
                    message="attachment exceeds the parser size limit",
                )
                await self.repository.commit()
                raise ValueError("attachment exceeds the parser size limit")
            content = await anyio.to_thread.run_sync(path.read_bytes)
            if len(content) > self.max_file_bytes:
                attempt_started = True
                attachment.parse_attempted_at = datetime.now(UTC)
                self._mark_failure(
                    attachment,
                    status="failed",
                    error_code="ATTACHMENT_TOO_LARGE",
                    retryable=False,
                    message="attachment exceeds the parser size limit",
                )
                await self.repository.commit()
                raise ValueError("attachment exceeds the parser size limit")
            content_hash = hashlib.sha256(content).hexdigest()
            detected = detect_attachment_type(
                content_type=attachment.mime_type,
                content=content,
                original_filename=attachment.attachment_name,
                source_url=attachment.download_final_url or attachment.source_url,
            )
            if detected.file_type in {"doc", "xls", "legacy_office"}:
                attempt_started = True
                attachment.parse_attempted_at = datetime.now(UTC)
                attachment.file_hash = content_hash
                attachment.file_size = len(content)
                attachment.file_type = detected.file_type
                attachment.file_extension = detected.extension or None
                attachment.type_detection_source = detected.source
                attachment.parser = None
                attachment.parser_version = None
                attachment.parsed_text = None
                attachment.extracted_text_length = 0
                _reset_ocr_audit(attachment)
                self._mark_failure(
                    attachment,
                    status="unsupported",
                    error_code="UNSUPPORTED_LEGACY_FORMAT",
                    retryable=False,
                    message="legacy Office bytes do not have a reliable parser",
                )
                await self.repository.commit()
                raise ValueError("legacy Office format is unsupported")
            expected_parser = "ocr" if requires_ocr_file else parser.__class__.__name__
            expected_parser_version = (
                _ocr_parser_version(parser) if requires_ocr_file else _parser_version(parser)
            )
            if (
                not force
                and not requires_ocr_file
                and attachment.parser == "ocr"
                and _parsed_cache_valid(
                    attachment,
                    content_hash=content_hash,
                    parser="ocr",
                    parser_version=_ocr_parser_version(parser),
                    ocr_provider=self.ocr_provider,
                )
            ):
                return _cached_artifact(attachment)
            if not force and _parsed_cache_valid(
                attachment,
                content_hash=content_hash,
                parser=expected_parser,
                parser_version=expected_parser_version,
                ocr_provider=self.ocr_provider,
            ):
                return _cached_artifact(attachment)
            attempt_started = True
            attachment.parse_attempted_at = datetime.now(UTC)
            attachment.processed_at = None
            attachment.file_hash = content_hash
            attachment.file_size = len(content)
            attachment.error_code = None
            attachment.retryable = False
            attachment.error_message = None
            if requires_ocr_file:
                return await self._ocr_attachment(
                    attachment,
                    content,
                    filename,
                    parser_version=expected_parser_version,
                )
            assert parser is not None
            parsed = parser.parse(content, filename=filename)
            attachment.parser = parser.__class__.__name__
            attachment.parser_version = _parser_version(parser)
            attachment.extraction_method = attachment.file_type or "parser"
            attachment.parsed_text = (
                "\f".join(clean_text(page) for page in parsed.pages)
                if parsed.pages
                else clean_text(parsed.text)
            )
            attachment.extracted_text_length = len(attachment.parsed_text or "")
            attachment.page_count = len(parsed.pages) or parsed.metadata.get("page_count")
            attachment.requires_ocr = parsed.requires_ocr
            if parsed.requires_ocr:
                return await self._ocr_attachment(
                    attachment,
                    content,
                    filename,
                    parser_version=_ocr_parser_version(parser),
                )
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
            _reset_ocr_audit(attachment)
            attachment.error_code = None
            attachment.retryable = False
            attachment.error_message = None
            attachment.processed_at = datetime.now(UTC)
            await self.repository.commit()
            return parsed
        except Exception:
            if not attempt_started:
                attachment.parse_attempted_at = datetime.now(UTC)
                attachment.error_code = None
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

    async def _ocr_attachment(
        self,
        attachment: Attachment,
        content: bytes,
        filename: str,
        *,
        parser_version: str,
    ) -> ParsedArtifact:
        attachment.requires_ocr = True
        attachment.parser = "ocr"
        attachment.parser_version = parser_version
        attachment.extraction_method = "pdf_ocr" if attachment.file_type == "pdf" else "image_ocr"
        attachment.ocr_page_count = 0
        attachment.ocr_text_length = 0
        attachment.ocr_latency_ms = 0
        if self.ocr_provider is None:
            attachment.ocr_status = "failed"
            attachment.ocr_provider = None
            attachment.ocr_version = None
            self._mark_failure(
                attachment,
                status="failed",
                error_code="OCR_PROVIDER_UNAVAILABLE",
                retryable=False,
                message="attachment requires OCR but no OCR provider is configured",
            )
            await self.repository.commit()
            raise ValueError("attachment requires OCR but no OCR provider is configured")
        provider_version = _ocr_provider_version(self.ocr_provider)
        attachment.ocr_provider = self.ocr_provider.name
        attachment.ocr_version = provider_version
        started_at = perf_counter()
        try:
            result = await self.ocr_provider.recognize(
                content,
                file_type=attachment.file_type,
                filename=filename,
            )
        except Exception:
            attachment.ocr_latency_ms = _elapsed_ms(started_at)
            attachment.ocr_status = "failed"
            self._mark_failure(
                attachment,
                status="failed",
                error_code="OCR_FAILED",
                retryable=True,
                message="OCR provider request failed",
            )
            await self.repository.commit()
            raise
        attachment.ocr_latency_ms = _elapsed_ms(started_at)
        text = (
            "\f".join(clean_text(page) for page in result.pages)
            if result.pages
            else clean_text(result.text)
        )
        attachment.ocr_provider = _resolved_identity(result.provider, self.ocr_provider.name)
        attachment.ocr_version = _resolved_identity(result.version, provider_version)
        attachment.ocr_status = result.status
        attachment.ocr_page_count = len(result.pages)
        attachment.ocr_text_length = len(text)
        attachment.parsed_text = text or None
        attachment.extracted_text_length = len(text)
        attachment.page_count = len(result.pages) or attachment.page_count
        if result.status == "failed" or not text:
            self._mark_failure(
                attachment,
                status="failed",
                error_code=result.error_code or "OCR_FAILED",
                retryable=False,
                message=result.error_message or "OCR provider produced no text",
            )
            await self.repository.commit()
            raise ValueError("attachment OCR failed")
        attachment.parse_status = "parsed"
        attachment.requires_ocr = False
        attachment.error_code = None
        attachment.retryable = False
        attachment.error_message = result.error_message
        attachment.processed_at = datetime.now(UTC)
        await self.repository.commit()
        return ParsedArtifact(
            text=text,
            pages=result.pages,
            metadata={
                "parser": "ocr",
                "parser_version": attachment.parser_version,
                "ocr_provider": attachment.ocr_provider,
                "ocr_version": attachment.ocr_version,
            },
        )

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
        attachment.processed_at = datetime.now(UTC)


def _filename(attachment: Attachment) -> str:
    extension = (attachment.file_extension or "").strip()
    if extension:
        return f"attachment.{extension.lstrip('.')}"
    for candidate in (
        attachment.attachment_name,
        urlsplit(attachment.source_url).path,
        attachment.local_path,
    ):
        if candidate and _safe_suffix(candidate):
            return Path(candidate).name
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


def _parser_version(parser: Parser | None) -> str:
    return str(getattr(parser, "version", "unknown"))


def _ocr_parser_version(parser: Parser | None) -> str:
    if parser is None:
        return f"ocr:{_OCR_PIPELINE_VERSION}"
    return f"{parser.__class__.__name__}:{_parser_version(parser)}+ocr:{_OCR_PIPELINE_VERSION}"


def _ocr_provider_version(provider: OcrProvider) -> str:
    return str(getattr(provider, "version", "unknown"))


def _resolved_identity(value: str | None, fallback: str) -> str:
    normalized = (value or "").strip()
    return fallback if not normalized or normalized == "unknown" else normalized


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _cached_artifact(attachment: Attachment) -> ParsedArtifact:
    return ParsedArtifact(
        text=attachment.parsed_text or "",
        metadata={
            "parser": attachment.parser or "unknown",
            "parser_version": attachment.parser_version,
            "ocr_provider": attachment.ocr_provider,
            "ocr_version": attachment.ocr_version,
        },
    )


def _parsed_cache_valid(
    attachment: Attachment,
    *,
    content_hash: str,
    parser: str,
    parser_version: str,
    ocr_provider: OcrProvider | None,
) -> bool:
    if (
        attachment.parse_status != "parsed"
        or attachment.parsed_text is None
        or attachment.file_hash != content_hash
        or attachment.parser != parser
        or attachment.parser_version != parser_version
    ):
        return False
    if parser != "ocr":
        return True
    if not attachment.ocr_provider or not attachment.ocr_version:
        return False
    if ocr_provider is None:
        return True
    return (
        attachment.ocr_provider == ocr_provider.name
        and attachment.ocr_version == _ocr_provider_version(ocr_provider)
    )


def _reset_ocr_audit(attachment: Attachment) -> None:
    attachment.requires_ocr = False
    attachment.ocr_status = "not_required"
    attachment.ocr_provider = None
    attachment.ocr_version = None
    attachment.ocr_page_count = None
    attachment.ocr_text_length = None
    attachment.ocr_latency_ms = None
