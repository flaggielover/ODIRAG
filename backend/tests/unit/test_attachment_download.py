from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest

from app.crawler import FetchResponse, ResponseTooLargeError, UnsafeUrlError
from app.crawler.storage import FileStorage
from app.services.attachment_download import AttachmentDownloadService


class _Attachment:
    def __init__(
        self,
        *,
        attachment_id: int = 1,
        name: str = "通知",
        url: str = "https://gov.example/download?id=1",
    ) -> None:
        self.id = attachment_id
        self.document_id = 7
        self.attachment_name = name
        self.source_url = url
        self.local_path: str | None = None
        self.mime_type: str | None = None
        self.file_extension: str | None = None
        self.file_type = "unknown"
        self.file_size: int | None = None
        self.file_hash: str | None = None
        self.download_http_status: int | None = None
        self.download_final_url: str | None = None
        self.download_error_code: str | None = None
        self.download_retryable = False
        self.download_status = "pending"
        self.parse_status = "pending"
        self.type_detection_source: str | None = None
        self.error_code: str | None = None
        self.retryable = False
        self.error_message: str | None = None
        self.processed_at = None


class _Repository:
    def __init__(self, attachment: _Attachment) -> None:
        self.attachment = attachment
        self.commits = 0

    async def get_attachment(self, attachment_id: int) -> _Attachment | None:
        return self.attachment if attachment_id == self.attachment.id else None

    async def commit(self) -> None:
        self.commits += 1


class _Fetcher:
    def __init__(self, result: FetchResponse | Exception) -> None:
        self.result = result
        self.calls = 0

    async def fetch(self, _url: str) -> FetchResponse:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _storage(path: Path) -> FileStorage:
    return FileStorage(
        path,
        max_bytes=1024 * 1024,
        allowed_extensions={
            ".docx",
            ".html",
            ".jpg",
            ".pdf",
            ".png",
            ".txt",
            ".webp",
            ".xlsx",
        },
    )


@pytest.fixture
def storage_path() -> Path:
    path = Path(".test-data") / "attachment-download"
    path.mkdir(parents=True, exist_ok=True)
    return path


async def test_download_detects_pdf_from_bytes_and_content_disposition(storage_path: Path) -> None:
    attachment = _Attachment()
    repository = _Repository(attachment)
    content = b"%PDF-1.7\n"
    fetcher = _Fetcher(
        FetchResponse(
            "https://gov.example/final",
            200,
            content,
            "application/octet-stream",
            "utf-8",
            "attachment; filename*=UTF-8''%E9%80%9A%E7%9F%A5.pdf",
        )
    )

    result = await AttachmentDownloadService(repository, fetcher, _storage(storage_path)).download(
        1
    )

    assert result.status == "completed"
    assert result.file_type == "pdf"
    assert attachment.download_http_status == 200
    assert attachment.download_final_url == "https://gov.example/final"
    assert attachment.type_detection_source == "content_disposition"
    assert attachment.file_hash == hashlib.sha256(content).hexdigest()
    assert attachment.local_path is not None
    assert await asyncio.to_thread(Path(attachment.local_path).read_bytes) == content
    assert attachment.parse_status == "pending"


async def test_download_marks_legacy_office_as_unsupported(storage_path: Path) -> None:
    attachment = _Attachment(name="历史材料.doc")
    repository = _Repository(attachment)
    fetcher = _Fetcher(
        FetchResponse(
            attachment.source_url,
            200,
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
            "application/octet-stream",
            "utf-8",
        )
    )

    result = await AttachmentDownloadService(repository, fetcher, _storage(storage_path)).download(
        1
    )

    assert result.status == "unsupported"
    assert result.error_code == "UNSUPPORTED_LEGACY_FORMAT"
    assert attachment.parse_status == "unsupported"
    assert attachment.download_status == "completed"
    assert attachment.retryable is False


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (UnsafeUrlError("blocked"), "DOWNLOAD_SSRF_BLOCKED", False),
        (ResponseTooLargeError("large"), "DOWNLOAD_TOO_LARGE", False),
        (httpx.ReadTimeout("timeout"), "DOWNLOAD_TIMEOUT", True),
    ],
)
async def test_download_records_stable_security_and_transport_errors(
    storage_path: Path,
    error: Exception,
    code: str,
    retryable: bool,
) -> None:
    attachment = _Attachment()
    repository = _Repository(attachment)

    result = await AttachmentDownloadService(
        repository, _Fetcher(error), _storage(storage_path)
    ).download(1)

    assert result.status == "failed"
    assert result.error_code == code
    assert attachment.download_error_code == code
    assert attachment.download_retryable is retryable
    assert attachment.parse_status == "failed"
    assert attachment.retryable is retryable


async def test_download_is_hash_idempotent_and_skips_network(storage_path: Path) -> None:
    attachment = _Attachment()
    content = b"already downloaded"
    local = storage_path / "existing.txt"
    local.write_bytes(content)
    attachment.local_path = str(local)
    attachment.file_hash = hashlib.sha256(content).hexdigest()
    attachment.file_type = "txt"
    attachment.download_status = "completed"
    repository = _Repository(attachment)
    fetcher = _Fetcher(AssertionError("network must not be called"))

    result = await AttachmentDownloadService(repository, fetcher, _storage(storage_path)).download(
        1
    )

    assert result.cache_hit is True
    assert fetcher.calls == 0
    assert repository.commits == 0


async def test_failed_download_state_cannot_return_a_successful_cache_hit(
    storage_path: Path,
) -> None:
    attachment = _Attachment()
    old_content = b"old downloaded bytes"
    local = storage_path / "existing.txt"
    local.write_bytes(old_content)
    attachment.local_path = str(local)
    attachment.file_hash = hashlib.sha256(old_content).hexdigest()
    attachment.file_type = "txt"
    attachment.download_status = "failed"
    attachment.download_error_code = "DOWNLOAD_TIMEOUT"
    repository = _Repository(attachment)
    fetcher = _Fetcher(httpx.ReadTimeout("timeout"))

    result = await AttachmentDownloadService(repository, fetcher, _storage(storage_path)).download(
        1
    )

    assert result.status == "failed"
    assert result.cache_hit is False
    assert fetcher.calls == 1


async def test_failed_force_retry_preserves_valid_parsed_bytes_and_identity(
    storage_path: Path,
) -> None:
    attachment = _Attachment()
    old_content = b"verified parsed bytes"
    local = storage_path / "existing.txt"
    local.write_bytes(old_content)
    old_hash = hashlib.sha256(old_content).hexdigest()
    attachment.local_path = str(local)
    attachment.file_hash = old_hash
    attachment.file_size = len(old_content)
    attachment.file_type = "txt"
    attachment.download_status = "completed"
    attachment.parse_status = "parsed"
    repository = _Repository(attachment)
    fetcher = _Fetcher(httpx.ReadTimeout("timeout"))

    result = await AttachmentDownloadService(repository, fetcher, _storage(storage_path)).download(
        1, force=True
    )

    assert result.status == "failed"
    assert attachment.download_status == "failed"
    assert attachment.download_error_code == "DOWNLOAD_TIMEOUT"
    assert attachment.parse_status == "parsed"
    assert attachment.local_path == str(local)
    assert attachment.file_hash == old_hash
    assert attachment.file_size == len(old_content)
    assert local.read_bytes() == old_content
