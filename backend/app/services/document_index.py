from __future__ import annotations

import anyio

from app.repositories.indexing import IndexRepository
from app.runtime import ApplicationRuntime
from app.services.bm25 import BM25RebuildService


async def rebuild_runtime_bm25(repository: IndexRepository, runtime: ApplicationRuntime) -> None:
    """Replace the in-process index first, then atomically persist its restart snapshot."""
    runtime.bm25_index = await BM25RebuildService(repository).build_index()
    await anyio.to_thread.run_sync(runtime.bm25_index.save, runtime.bm25_snapshot_path)


async def invalidate_document_retrieval(
    document_id: int,
    repository: IndexRepository,
    runtime: ApplicationRuntime,
) -> None:
    """Remove all current and historic vector points before excluding a stale document."""
    point_ids = await repository.vector_point_ids_for_document(document_id)
    if point_ids:
        await runtime.vector_store.delete(sorted(point_ids))
    await repository.set_chunk_vector_status(document_id, "stale")
    await repository.commit()
    await rebuild_runtime_bm25(repository, runtime)
