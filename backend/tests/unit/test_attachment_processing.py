from __future__ import annotations

from types import SimpleNamespace

from app.services.attachment_download import AttachmentDownloadResult
from app.services.attachment_processing import AttachmentProcessingService


class _Session:
    async def refresh(self, instance: object) -> None:
        del instance


class _Repository:
    def __init__(self, rows: dict[int, SimpleNamespace]) -> None:
        self.rows = rows
        self.session = _Session()

    async def get_attachment(self, attachment_id: int) -> SimpleNamespace | None:
        return self.rows.get(attachment_id)


class _Downloader:
    def __init__(self, rows: dict[int, SimpleNamespace]) -> None:
        self.rows = rows
        self.calls: list[int] = []

    async def download(
        self, attachment_id: int, *, force: bool = False
    ) -> AttachmentDownloadResult:
        del force
        self.calls.append(attachment_id)
        row = self.rows[attachment_id]
        if attachment_id == 2:
            row.download_status = "failed"
            row.parse_status = "failed"
            row.download_error_code = "DOWNLOAD_TIMEOUT"
            row.error_code = "DOWNLOAD_TIMEOUT"
            return AttachmentDownloadResult(
                attachment_id,
                "failed",
                row.file_type,
                error_code="DOWNLOAD_TIMEOUT",
            )
        row.download_status = "completed"
        return AttachmentDownloadResult(
            attachment_id,
            "completed",
            row.file_type,
            cache_hit=True,
        )


class _Parser:
    def __init__(self, rows: dict[int, SimpleNamespace]) -> None:
        self.rows = rows
        self.calls: list[int] = []

    async def parse_attachment(self, attachment_id: int, *, force: bool = False) -> None:
        del force
        self.calls.append(attachment_id)
        row = self.rows[attachment_id]
        row.parse_status = "parsed"
        row.parser = "TextParser"
        row.parser_version = "1"
        row.file_hash = "byte-derived-hash"
        row.error_code = None


def _row(attachment_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=attachment_id,
        download_status="pending",
        parse_status="pending",
        file_type="txt",
        download_error_code=None,
        error_code=None,
        parser=None,
        parser_version=None,
        file_hash=None,
    )


async def test_processing_is_sequential_and_parses_only_completed_downloads() -> None:
    rows = {1: _row(1), 2: _row(2), 3: _row(3)}
    repository = _Repository(rows)
    downloader = _Downloader(rows)
    parser = _Parser(rows)
    service = AttachmentProcessingService(repository, downloader, parser)  # type: ignore[arg-type]

    results = await service.process_many([3, 2, 1])

    assert downloader.calls == [3, 2, 1]
    assert parser.calls == [3, 1]
    assert [result.attachment_id for result in results] == [3, 2, 1]
    assert results[0].download_cache_hit is True
    assert results[0].parse_status == "parsed"
    assert results[1].parse_status == "failed"
    assert results[1].error_code == "DOWNLOAD_TIMEOUT"
