from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from app.chunking import ChunkDraft, HeadingAwareChunker
from app.embedding import EmbeddingBatcher
from app.errors import ConflictError, NotFoundError
from app.models import Attachment, Chunk, DataLineage, Document
from app.providers import ProviderResponseError
from app.repositories.indexing import IndexRepository
from app.vector_store import VectorPoint, VectorStore

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _SourceDraft:
    index: int
    content: str
    section_path: tuple[str, ...]
    section_title: str | None
    char_count: int
    attachment_id: int | None
    page_number: int | None


@dataclass(frozen=True, slots=True)
class IndexingResult:
    document_id: int
    document_version: int
    chunk_count: int
    cache_hits: int
    embedded_count: int
    embedding_model: str
    embedding_version: str
    estimated_cost: float
    vector_point_ids: tuple[str, ...]


class IndexingService:
    def __init__(
        self,
        repository: IndexRepository,
        chunker: HeadingAwareChunker,
        embedding_batcher: EmbeddingBatcher,
        vector_store: VectorStore,
        *,
        dimensions: int,
        embedding_version: str = "v1",
    ) -> None:
        self.repository = repository
        self.chunker = chunker
        self.embedding_batcher = embedding_batcher
        self.vector_store = vector_store
        self.dimensions = dimensions
        self.embedding_version = embedding_version

    async def index_document(self, document_id: int) -> IndexingResult:
        document = await self.repository.get_document(document_id)
        if document is None:
            raise NotFoundError("Document", document_id)
        if document.final_status != "approved":
            raise ConflictError(
                "Only approved documents can be indexed",
                {"document_id": document_id, "final_status": document.final_status},
            )
        database_id = document.id
        attachments = await self.repository.list_indexable_attachments(document.id)
        drafts = self._drafts(document, attachments)
        if not drafts:
            raise ConflictError("Document content did not produce any indexable chunks")
        existing_chunks = await self.repository.list_document_chunks(document.id)
        await self.repository.set_document_index_status(document.id, "indexing")
        await self.repository.commit()
        database_switched = False
        new_only_ids: set[str] = set()
        try:
            embedding_result = await self.embedding_batcher.embed(
                [draft.content for draft in drafts]
            )
            vectors = [list(vector) for vector in embedding_result.vectors]
            if any(len(vector) != self.dimensions for vector in vectors):
                raise ProviderResponseError(
                    "embedding",
                    f"vector dimensions do not match configured size {self.dimensions}",
                )
            await self.vector_store.ensure_collection(self.dimensions)
            chunks = [self._chunk(document, draft) for draft in drafts]
            points = [
                VectorPoint(
                    point_id=chunk.chunk_id,
                    vector=vector,
                    document_id=document.document_id,
                    content=chunk.content,
                    title=document.title,
                    source_url=document.source_url,
                    payload=self._payload(document, chunk),
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
            current_ids = {point.point_id for point in points}
            existing_ids = {chunk.chunk_id for chunk in existing_chunks}
            new_only_ids = current_ids - existing_ids
            await self.vector_store.upsert(points)
            replace_required = self._replace_required(existing_chunks, chunks)
            if replace_required:
                await self.repository.replace_chunks(document.id, chunks)
                version_id = await self.repository.ensure_document_version(document)
                crawl_task_id = await self.repository.latest_crawl_task_id(document.id)
                await self.repository.add_lineages(
                    [
                        DataLineage(
                            lineage_id=str(uuid.uuid4()),
                            source_id=document.source_id,
                            crawl_task_id=crawl_task_id,
                            document_id=document.id,
                            document_version_id=version_id,
                            attachment_id=chunk.attachment_id,
                            chunk_id=chunk.id,
                            vector_point_id=chunk.chunk_id,
                        )
                        for chunk in chunks
                    ]
                )
            await self.repository.commit()
            database_switched = True
            stale_ids = existing_ids - current_ids
            stale_ids.update(
                await self.repository.orphaned_vector_point_ids(document.id, current_ids)
            )
            if stale_ids:
                await self.vector_store.delete(sorted(stale_ids))
            await self.repository.set_chunk_vector_status(document.id, "indexed")
            await self.repository.set_document_index_status(document.id, "indexed")
            await self.repository.commit()
            return IndexingResult(
                document_id=document.id,
                document_version=document.version,
                chunk_count=len(chunks),
                cache_hits=embedding_result.cache_hits,
                embedded_count=embedding_result.embedded_count,
                embedding_model=self.embedding_batcher.provider.model_name,
                embedding_version=self.embedding_version,
                estimated_cost=embedding_result.estimated_cost,
                vector_point_ids=tuple(chunk.chunk_id for chunk in chunks),
            )
        except Exception:
            await self.repository.rollback()
            if new_only_ids and not database_switched:
                try:
                    await self.vector_store.delete(sorted(new_only_ids))
                except Exception as compensation_error:
                    logger.error(
                        "vector_compensation_failed",
                        document_id=document.id,
                        error=str(compensation_error),
                    )
            await self.repository.set_document_index_status(database_id, "failed")
            await self.repository.commit()
            raise

    async def list_chunks(self, document_id: int) -> list[Chunk]:
        if await self.repository.get_document(document_id) is None:
            raise NotFoundError("Document", document_id)
        return await self.repository.list_document_chunks(document_id)

    def _chunk(self, document: Document, draft: _SourceDraft) -> Chunk:
        digest = hashlib.sha256(draft.content.encode("utf-8")).hexdigest()
        point_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"odirag:{document.document_id}:{document.version}:{draft.attachment_id}:"
                f"{draft.page_number}:{draft.index}:{draft.section_path}:{draft.section_title}:"
                f"{self.embedding_batcher.provider.provider_name}:"
                f"{self.embedding_batcher.provider.model_name}:{self.embedding_version}:{digest}",
            )
        )
        return Chunk(
            chunk_id=point_id,
            document_id=document.id,
            attachment_id=draft.attachment_id,
            chunk_index=draft.index,
            section_path=" > ".join(draft.section_path) or None,
            section_title=draft.section_title,
            page_number=draft.page_number,
            content=draft.content,
            content_hash=digest,
            char_count=draft.char_count,
            token_count=_token_count(draft.content),
            embedding_model=self.embedding_batcher.provider.model_name,
            embedding_version=self.embedding_version,
            vector_status="pending",
        )

    def _drafts(self, document: Document, attachments: list[Attachment]) -> list[_SourceDraft]:
        drafts: list[_SourceDraft] = []
        self._append_drafts(drafts, self.chunker.chunk(document.content), None, None)
        for attachment in attachments:
            pages = (attachment.parsed_text or "").split("\f")
            has_pages = len(pages) > 1 or attachment.page_count is not None
            for page_index, page in enumerate(pages, start=1):
                page_drafts = self.chunker.chunk(page)
                self._append_drafts(
                    drafts,
                    page_drafts,
                    attachment,
                    page_index if has_pages else None,
                )
        return drafts

    @staticmethod
    def _append_drafts(
        output: list[_SourceDraft],
        drafts: list[ChunkDraft],
        attachment: Attachment | None,
        page_number: int | None,
    ) -> None:
        for draft in drafts:
            path = draft.section_path
            title = draft.section_title
            if attachment is not None:
                path = (attachment.attachment_name, *path)
                title = title or attachment.attachment_name
            output.append(
                _SourceDraft(
                    index=len(output),
                    content=draft.content,
                    section_path=path,
                    section_title=title,
                    char_count=draft.char_count,
                    attachment_id=attachment.id if attachment is not None else None,
                    page_number=page_number,
                )
            )

    def _replace_required(self, existing_chunks: list[Chunk], desired_chunks: list[Chunk]) -> bool:
        if len(existing_chunks) != len(desired_chunks):
            return True
        return any(
            existing.chunk_id != desired.chunk_id
            or existing.embedding_model != desired.embedding_model
            or existing.embedding_version != desired.embedding_version
            for existing, desired in zip(existing_chunks, desired_chunks, strict=True)
        )

    @staticmethod
    def _payload(document: Document, chunk: Chunk) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_id": document.source_id,
            "source_name": document.source.name if document.source is not None else None,
            "official_status": (
                document.source.official_status if document.source is not None else None
            ),
            "region": document.region,
            "city": document.city,
            "document_type": document.document_type,
            "issuing_authority": document.issuing_authority,
            "document_number": document.document_number,
            "publish_date": (document.publish_date.isoformat() if document.publish_date else None),
            "document_version": document.version,
            "section_path": chunk.section_path,
            "section_title": chunk.section_title,
            "page_number": chunk.page_number,
            "content_hash": chunk.content_hash,
        }
        return {key: value for key, value in payload.items() if value is not None}


def _token_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text))
