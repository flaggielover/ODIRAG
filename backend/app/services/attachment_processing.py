from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass

from app.repositories.documents import DocumentRepository
from app.services.attachment_download import AttachmentDownloadService
from app.services.parsing import ParsingService


@dataclass(frozen=True, slots=True)
class AttachmentProcessingResult:
    attachment_id: int
    download_status: str
    parse_status: str
    file_type: str
    download_cache_hit: bool
    error_code: str | None
    parser: str | None
    parser_version: str | None
    content_hash: str | None


class AttachmentProcessingService:
    """Run a bounded, sequential download/parse pass over explicit rows."""

    def __init__(
        self,
        repository: DocumentRepository,
        downloader: AttachmentDownloadService,
        parser: ParsingService,
    ) -> None:
        self.repository = repository
        self.downloader = downloader
        self.parser = parser

    async def process_one(
        self,
        attachment_id: int,
        *,
        force: bool = False,
    ) -> AttachmentProcessingResult:
        download = await self.downloader.download(attachment_id, force=force)
        if download.status == "completed" and download.error_code is None:
            # ParsingService persists a sanitized terminal outcome before raising.
            with suppress(Exception):
                await self.parser.parse_attachment(attachment_id, force=force)

        attachment = await self.repository.get_attachment(attachment_id)
        if attachment is None:
            raise RuntimeError(f"attachment {attachment_id} disappeared during processing")
        await self.repository.session.refresh(attachment)
        return AttachmentProcessingResult(
            attachment_id=attachment.id,
            download_status=attachment.download_status,
            parse_status=attachment.parse_status,
            file_type=attachment.file_type,
            download_cache_hit=download.cache_hit,
            error_code=attachment.error_code or attachment.download_error_code,
            parser=attachment.parser,
            parser_version=attachment.parser_version,
            content_hash=attachment.file_hash,
        )

    async def process_many(
        self,
        attachment_ids: list[int],
        *,
        force: bool = False,
    ) -> list[AttachmentProcessingResult]:
        results: list[AttachmentProcessingResult] = []
        for attachment_id in attachment_ids:
            results.append(await self.process_one(attachment_id, force=force))
        return results
