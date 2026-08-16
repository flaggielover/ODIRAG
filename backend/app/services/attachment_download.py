from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import anyio

from app.attachments import DetectedAttachmentType, detect_attachment_type
from app.crawler import Fetcher, FetchResponse
from app.crawler.storage import FileStorage
from app.models import Attachment
from app.repositories.documents import DocumentRepository


@dataclass(frozen=True, slots=True)
class AttachmentDownloadResult:
    attachment_id: int
    status: str
    file_type: str
    cache_hit: bool = False
    error_code: str | None = None


class AttachmentDownloadService:
    """Download URL-only attachments through the existing SSRF-safe Fetcher."""

    def __init__(
        self,
        repository: DocumentRepository,
        fetcher: Fetcher,
        storage: FileStorage,
    ) -> None:
        self.repository = repository
        self.fetcher = fetcher
        self.storage = storage

    async def download(
        self, attachment_id: int, *, force: bool = False
    ) -> AttachmentDownloadResult:
        attachment = await self.repository.get_attachment(attachment_id)
        if attachment is None:
            raise ValueError(f"attachment {attachment_id} does not exist")
        has_valid_local_bytes = False
        if attachment.local_path and attachment.file_hash:
            has_valid_local_bytes = await _same_hash(
                Path(attachment.local_path), attachment.file_hash
            )
        if (
            not force
            and attachment.local_path
            and attachment.file_hash
            and has_valid_local_bytes
            and attachment.download_status == "completed"
            and attachment.download_error_code is None
        ):
            return AttachmentDownloadResult(
                attachment.id,
                "completed",
                attachment.file_type,
                cache_hit=True,
            )
        attachment.download_http_status = None
        attachment.download_final_url = None
        try:
            response = await self.fetcher.fetch(attachment.source_url)
            attachment.download_http_status = response.status_code
            attachment.download_final_url = response.url
            content_hash = _sha256(response.content)
            detected = detect_attachment_type(
                content_type=response.content_type,
                content_disposition=response.content_disposition,
                content=response.content,
                original_filename=attachment.attachment_name,
                source_url=response.url,
            )
            if detected.file_type not in _SUPPORTED_TYPES and detected.file_type not in _OCR_TYPES:
                code = (
                    "UNSUPPORTED_LEGACY_FORMAT"
                    if detected.file_type in {"doc", "xls", "legacy_office"}
                    else "UNSUPPORTED_FILE_TYPE"
                )
                _record_download_success(
                    attachment,
                    response=response,
                    content_hash=content_hash,
                    detected=detected,
                )
                attachment.parse_status = "unsupported"
                attachment.error_code = code
                attachment.retryable = False
                attachment.error_message = (
                    f"no reliable parser is registered for {detected.file_type}"
                )
                attachment.processed_at = datetime.now(UTC)
                await self.repository.commit()
                return AttachmentDownloadResult(
                    attachment.id,
                    "unsupported",
                    detected.file_type,
                    error_code=code,
                )
            filename = _filename_for(detected, attachment.attachment_name)
            path = self.storage.save(
                source_url=response.url,
                content=response.content,
                namespace=str(attachment.document_id),
                filename=filename,
                identity=f"attachment-{attachment.id}",
                expected_sha256=content_hash,
            )
            _record_download_success(
                attachment,
                response=response,
                content_hash=content_hash,
                detected=detected,
            )
            attachment.local_path = str(path)
            attachment.parse_status = "pending"
            attachment.error_code = None
            attachment.retryable = False
            attachment.error_message = None
            attachment.processed_at = None
            await self.repository.commit()
            return AttachmentDownloadResult(attachment.id, "completed", detected.file_type)
        except Exception as exc:
            code, retryable = _download_error(exc)
            error_response = getattr(exc, "response", None)
            if error_response is not None:
                attachment.download_http_status = getattr(error_response, "status_code", None)
                attachment.download_final_url = str(getattr(error_response, "url", "")) or None
            attachment.download_status = "failed"
            attachment.download_error_code = code
            attachment.download_retryable = retryable
            attachment.processed_at = datetime.now(UTC)
            if not has_valid_local_bytes or attachment.parse_status != "parsed":
                attachment.parse_status = "failed"
                attachment.error_code = code
                attachment.retryable = retryable
                attachment.error_message = f"attachment download failed: {code}"
            await self.repository.commit()
            return AttachmentDownloadResult(
                attachment.id,
                "failed",
                attachment.file_type,
                error_code=code,
            )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


async def _same_hash(path: Path, expected: str) -> bool:
    if not await anyio.to_thread.run_sync(path.is_file):
        return False
    actual = await anyio.to_thread.run_sync(_sha256_file, path)
    return actual == expected


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_download_success(
    attachment: Attachment,
    *,
    response: FetchResponse,
    content_hash: str,
    detected: DetectedAttachmentType,
) -> None:
    attachment.download_http_status = response.status_code
    attachment.download_final_url = response.url
    attachment.mime_type = response.content_type
    attachment.file_size = len(response.content)
    attachment.file_hash = content_hash
    attachment.file_type = detected.file_type
    attachment.file_extension = detected.extension or None
    attachment.type_detection_source = detected.source
    attachment.download_status = "completed"
    attachment.download_error_code = None
    attachment.download_retryable = False


def _filename_for(detected: DetectedAttachmentType, fallback: str) -> str:
    filename = detected.filename or fallback or "attachment"
    stem = Path(filename).stem or "attachment"
    return f"{stem}{detected.extension}" if detected.extension else filename


_SUPPORTED_TYPES = {"pdf", "docx", "xlsx", "txt", "html"}
_OCR_TYPES = {"jpg", "png", "webp"}


def _download_error(error: Exception) -> tuple[str, bool]:
    name = error.__class__.__name__
    if name in {
        "TimeoutError",
        "ReadTimeout",
        "ConnectTimeout",
        "PoolTimeout",
        "WriteTimeout",
    }:
        return "DOWNLOAD_TIMEOUT", True
    if name == "UnsafeUrlError":
        return "DOWNLOAD_SSRF_BLOCKED", False
    if name == "ResponseTooLargeError":
        return "DOWNLOAD_TOO_LARGE", False
    if name == "RedirectLimitError":
        return "DOWNLOAD_REDIRECT_LIMIT", False
    if name in {"ConnectError", "NetworkError", "RemoteProtocolError", "ReadError"}:
        return "DOWNLOAD_TRANSPORT_ERROR", True
    if name == "HTTPStatusError":
        status = getattr(getattr(error, "response", None), "status_code", 0)
        if status == 429:
            return "DOWNLOAD_HTTP_429", True
        if status >= 500:
            return "DOWNLOAD_HTTP_5XX", True
        return f"DOWNLOAD_HTTP_{status}", False
    return "DOWNLOAD_ERROR", False
