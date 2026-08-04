from __future__ import annotations

from pathlib import Path

import anyio

from app.cleaners import clean_text
from app.errors import NotFoundError
from app.parsers import ParsedArtifact, ParserRegistry
from app.repositories.documents import DocumentRepository
from app.services.versioning import VersioningResult, VersioningService


class ParsingService:
    def __init__(
        self,
        repository: DocumentRepository,
        registry: ParserRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry or ParserRegistry()
        self.versioning = VersioningService(repository)

    async def parse_attachment(self, attachment_id: int) -> ParsedArtifact:
        attachment = await self.repository.get_attachment(attachment_id)
        if attachment is None:
            raise NotFoundError("Attachment", attachment_id)
        if not attachment.local_path:
            raise ValueError("attachment has no downloaded local path")
        path = Path(attachment.local_path)
        if not await anyio.to_thread.run_sync(path.is_file):
            raise FileNotFoundError(path)
        try:
            content = await anyio.to_thread.run_sync(path.read_bytes)
            parsed = self.registry.parse(path.name, content)
            attachment.parsed_text = (
                "\f".join(clean_text(page) for page in parsed.pages)
                if parsed.pages
                else clean_text(parsed.text)
            )
            attachment.page_count = len(parsed.pages) or parsed.metadata.get("page_count")
            attachment.requires_ocr = parsed.requires_ocr
            attachment.parse_status = "completed"
            attachment.error_message = None
            await self.repository.commit()
            return parsed
        except Exception as exc:
            attachment.parse_status = "failed"
            attachment.error_message = exc.__class__.__name__
            await self.repository.commit()
            raise

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
