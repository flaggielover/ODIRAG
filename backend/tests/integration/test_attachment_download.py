from __future__ import annotations

import httpx

from app.crawler import HttpFetcher
from app.crawler.storage import FileStorage
from app.models import Attachment, Document
from app.repositories.documents import DocumentRepository
from app.services.attachment_download import AttachmentDownloadService


async def _public_resolver(_hostname: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


async def _seed_attachment(session, *, name: str, url: str) -> Attachment:
    document = Document(
        document_id=f"DOWNLOAD-{name}",
        title="Attachment download fixture",
        source_url="https://example.gov/notice",
        content="Policy content",
        word_count=14,
        final_status="approved",
    )
    session.add(document)
    await session.flush()
    attachment = Attachment(
        document_id=document.id,
        attachment_name=name,
        source_url=url,
        download_status="pending",
        parse_status="pending",
    )
    session.add(attachment)
    await session.commit()
    return attachment


async def test_downloader_records_content_disposition_detection_and_hash_cache(app) -> None:
    content = b"plain policy attachment"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=content,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": "attachment; filename*=UTF-8''policy.txt",
            },
        )

    async with app.state.database.session_factory() as session:
        attachment = await _seed_attachment(
            session,
            name="政策附件",
            url="https://example.gov/download?id=1",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = AttachmentDownloadService(
                DocumentRepository(session),
                HttpFetcher(client=client, resolver=_public_resolver),
                FileStorage(
                    app.state.settings.data_dir / "download-test",
                    max_bytes=1024,
                    allowed_extensions={".txt"},
                ),
            )
            first = await service.download(attachment.id)
            second = await service.download(attachment.id)
        await session.refresh(attachment)

        assert first.status == "completed"
        assert second.cache_hit is True
        assert attachment.download_http_status == 200
        assert attachment.download_final_url == "https://example.gov/download?id=1"
        assert attachment.file_type == "txt"
        assert attachment.file_extension == ".txt"
        assert attachment.type_detection_source == "content_disposition"
        assert attachment.file_hash is not None
        assert attachment.local_path is not None


async def test_downloader_records_legacy_format_as_unsupported(app) -> None:
    content = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            content=content,
            headers={"Content-Type": "application/octet-stream"},
        )

    async with app.state.database.session_factory() as session:
        attachment = await _seed_attachment(
            session,
            name="历史材料.doc",
            url="https://example.gov/file?id=2",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await AttachmentDownloadService(
                DocumentRepository(session),
                HttpFetcher(client=client, resolver=_public_resolver),
                FileStorage(
                    app.state.settings.data_dir / "legacy-test",
                    max_bytes=1024,
                    allowed_extensions={".doc"},
                ),
            ).download(attachment.id)
        await session.refresh(attachment)

        assert result.status == "unsupported"
        assert attachment.parse_status == "unsupported"
        assert attachment.error_code == "UNSUPPORTED_LEGACY_FORMAT"
        assert attachment.retryable is False
        assert attachment.local_path is None


async def test_downloader_preserves_ssrf_failure_as_terminal_and_not_retryable(app) -> None:
    async with app.state.database.session_factory() as session:
        attachment = await _seed_attachment(
            session,
            name="blocked.pdf",
            url="http://127.0.0.1/private.pdf",
        )
        result = await AttachmentDownloadService(
            DocumentRepository(session),
            HttpFetcher(),
            FileStorage(
                app.state.settings.data_dir / "ssrf-test",
                max_bytes=1024,
                allowed_extensions={".pdf"},
            ),
        ).download(attachment.id)
        await session.refresh(attachment)

        assert result.status == "failed"
        assert attachment.error_code == "DOWNLOAD_SSRF_BLOCKED"
        assert attachment.download_error_code == "DOWNLOAD_SSRF_BLOCKED"
        assert attachment.retryable is False
        assert attachment.download_retryable is False
