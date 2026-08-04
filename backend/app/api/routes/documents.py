from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.config import Settings
from app.dependencies import (
    AdminUser,
    DatabaseSession,
    get_app_settings,
    get_application_runtime,
)
from app.errors import NotFoundError
from app.repositories.documents import DocumentRepository
from app.repositories.indexing import IndexRepository
from app.runtime import ApplicationRuntime
from app.schemas.document import (
    ChunkResponse,
    DocumentAttachmentResponse,
    DocumentDetailResponse,
    DocumentSummaryResponse,
    DocumentUpdate,
    DocumentVersionResponse,
    IndexDocumentResponse,
)
from app.services.document_index import invalidate_document_retrieval, rebuild_runtime_bm25
from app.services.indexing import IndexingService
from app.services.versioning import VersioningService

router = APIRouter(prefix="/documents", tags=["documents"])


def get_indexing_service(
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
    runtime: Annotated[ApplicationRuntime, Depends(get_application_runtime)],
) -> IndexingService:
    return IndexingService(
        IndexRepository(session),
        runtime.chunker,
        runtime.embedding_batcher,
        runtime.vector_store,
        dimensions=settings.embedding_dimensions,
        embedding_version=settings.embedding_version,
    )


IndexingServiceDependency = Annotated[IndexingService, Depends(get_indexing_service)]
RuntimeDependency = Annotated[ApplicationRuntime, Depends(get_application_runtime)]


def get_document_repository(session: DatabaseSession) -> DocumentRepository:
    return DocumentRepository(session)


DocumentRepositoryDependency = Annotated[DocumentRepository, Depends(get_document_repository)]


@router.get("", response_model=list[DocumentSummaryResponse])
async def list_documents(
    _admin: AdminUser,
    repository: DocumentRepositoryDependency,
    final_status: Annotated[str | None, Query(max_length=32)] = None,
    index_status: Annotated[str | None, Query(max_length=32)] = None,
    source_id: Annotated[int | None, Query(gt=0)] = None,
    q: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DocumentSummaryResponse]:
    documents = await repository.list(
        final_status=final_status,
        index_status=index_status,
        source_id=source_id,
        query=q,
        limit=limit,
    )
    return [DocumentSummaryResponse.model_validate(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: int,
    _admin: AdminUser,
    repository: DocumentRepositoryDependency,
) -> DocumentDetailResponse:
    document = await repository.get_detail(document_id)
    if document is None:
        raise NotFoundError("Document", document_id)
    return DocumentDetailResponse.model_validate(document)


@router.put("/{document_id}", response_model=DocumentDetailResponse)
async def update_document(
    document_id: int,
    payload: DocumentUpdate,
    _admin: AdminUser,
    repository: DocumentRepositoryDependency,
    runtime: RuntimeDependency,
) -> DocumentDetailResponse:
    document = await repository.get_detail(document_id)
    if document is None:
        raise NotFoundError("Document", document_id)
    result = await VersioningService(repository).apply_metadata_update(
        document_id, payload.model_dump(exclude_unset=True)
    )
    if result.changed:
        await invalidate_document_retrieval(
            document_id, IndexRepository(repository.session), runtime
        )
    refreshed = await repository.get_detail(document_id)
    if refreshed is None:
        raise NotFoundError("Document", document_id)
    return DocumentDetailResponse.model_validate(refreshed)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    _admin: AdminUser,
    repository: DocumentRepositoryDependency,
    runtime: RuntimeDependency,
) -> Response:
    document = await repository.get(document_id)
    if document is None:
        raise NotFoundError("Document", document_id)
    index_repository = IndexRepository(repository.session)
    point_ids = await index_repository.vector_point_ids_for_document(document_id)
    if point_ids:
        await runtime.vector_store.delete(sorted(point_ids))
    await repository.delete(document)
    await rebuild_runtime_bm25(index_repository, runtime)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/reparse", response_model=DocumentDetailResponse)
async def reparse_document(
    document_id: int,
    _admin: AdminUser,
    session: DatabaseSession,
    runtime: RuntimeDependency,
) -> DocumentDetailResponse:
    from app.services.parsing import ParsingService

    result = await ParsingService(DocumentRepository(session)).reparse_html_document(document_id)
    if result.changed:
        await invalidate_document_retrieval(document_id, IndexRepository(session), runtime)
    document = await DocumentRepository(session).get_detail(document_id)
    if document is None:
        raise NotFoundError("Document", document_id)
    return DocumentDetailResponse.model_validate(document)


@router.get("/{document_id}/attachments", response_model=list[DocumentAttachmentResponse])
async def document_attachments(
    document_id: int, _admin: AdminUser, repository: DocumentRepositoryDependency
) -> list[DocumentAttachmentResponse]:
    document = await repository.get_detail(document_id)
    if document is None:
        raise NotFoundError("Document", document_id)
    return [DocumentAttachmentResponse.model_validate(item) for item in document.attachments]


@router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
async def document_versions(
    document_id: int, _admin: AdminUser, repository: DocumentRepositoryDependency
) -> list[DocumentVersionResponse]:
    document = await repository.get_detail(document_id)
    if document is None:
        raise NotFoundError("Document", document_id)
    return [DocumentVersionResponse.model_validate(item) for item in document.versions]


@router.get("/{document_id}/lineage", response_model=list[dict[str, object]])
async def document_lineage(
    document_id: int, _admin: AdminUser, repository: DocumentRepositoryDependency
) -> list[dict[str, object]]:
    document = await repository.get_lineage(document_id)
    if document is None:
        raise NotFoundError("Document", document_id)
    return [
        {
            "id": item.id,
            "lineage_id": item.lineage_id,
            "source_id": item.source_id,
            "crawl_task_id": item.crawl_task_id,
            "document_id": item.document_id,
            "document_version_id": item.document_version_id,
            "attachment_id": item.attachment_id,
            "chunk_id": item.chunk_id,
            "vector_point_id": item.vector_point_id,
            "evaluation_run_id": item.evaluation_run_id,
            "created_at": item.created_at,
        }
        for item in document.lineage_records
    ]


@router.post("/{document_id}/reindex", response_model=IndexDocumentResponse)
async def reindex_document(
    document_id: int,
    _admin: AdminUser,
    session: DatabaseSession,
    service: IndexingServiceDependency,
    runtime: RuntimeDependency,
) -> IndexDocumentResponse:
    result = await service.index_document(document_id)
    await rebuild_runtime_bm25(IndexRepository(session), runtime)
    return IndexDocumentResponse(
        document_id=result.document_id,
        document_version=result.document_version,
        chunk_count=result.chunk_count,
        cache_hits=result.cache_hits,
        embedded_count=result.embedded_count,
        embedding_model=result.embedding_model,
        embedding_version=result.embedding_version,
        estimated_cost=result.estimated_cost,
        vector_point_ids=list(result.vector_point_ids),
        bm25_document_count=runtime.bm25_index.document_count,
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkResponse])
async def document_chunks(
    document_id: int, _admin: AdminUser, service: IndexingServiceDependency
) -> list[ChunkResponse]:
    return [ChunkResponse.model_validate(chunk) for chunk in await service.list_chunks(document_id)]
