from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Attachment,
    Chunk,
    CozeInvocation,
    CrawlTask,
    CrawlTaskFailure,
    DataLineage,
    Document,
    DocumentReview,
    DocumentVersion,
    SourceColumn,
)


class CrawlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_column(self, column_id: int) -> SourceColumn | None:
        result = await self.session.execute(
            select(SourceColumn)
            .where(SourceColumn.id == column_id)
            .options(selectinload(SourceColumn.source))
        )
        return result.scalar_one_or_none()

    async def create_task(self, task: CrawlTask) -> CrawlTask:
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get_task(self, task_id: int) -> CrawlTask | None:
        result = await self.session.execute(
            select(CrawlTask)
            .where(CrawlTask.id == task_id)
            .options(selectinload(CrawlTask.source_column).selectinload(SourceColumn.source))
        )
        return result.scalar_one_or_none()

    async def claim_task(self, task_id: int) -> CrawlTask | None:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(CrawlTask)
            .where(CrawlTask.id == task_id, CrawlTask.status.in_(["pending", "queued"]))
            .values(
                status="running",
                current_stage="running",
                started_at=now,
                finished_at=None,
                completed_at=None,
                error_message=None,
            )
        )
        await self.session.commit()
        if getattr(result, "rowcount", 0) != 1:
            return None
        return await self.get_task(task_id)

    async def advance_task_if_status(
        self,
        task_id: int,
        *,
        expected_status: str,
        target_status: str,
        provider_status: str,
        target_stage: str | None = None,
    ) -> bool:
        """Atomically advance a worker stage without overwriting a concurrent cancel."""

        result = await self.session.execute(
            update(CrawlTask)
            .where(CrawlTask.id == task_id, CrawlTask.status == expected_status)
            .values(
                status=target_status,
                current_stage=target_stage or target_status,
                provider_status=provider_status,
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        return getattr(result, "rowcount", 0) == 1

    async def cancel_task_if_status(
        self,
        task: CrawlTask,
        *,
        expected_status: str,
        provider_status: str,
        provider_error_message: str | None,
    ) -> bool:
        """Cancel only the state observed by the caller, preserving worker progress."""

        now = datetime.now(UTC)
        result = await self.session.execute(
            update(CrawlTask)
            .where(CrawlTask.id == task.id, CrawlTask.status == expected_status)
            .values(
                status="cancelled",
                current_stage="cancelled",
                provider_status=provider_status,
                provider_error_message=provider_error_message,
                finished_at=now,
                completed_at=now,
                error_message=None,
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        await self.session.refresh(task)
        return getattr(result, "rowcount", 0) == 1

    async def list_tasks(self, *, status: str | None = None) -> list[CrawlTask]:
        statement = select(CrawlTask).order_by(CrawlTask.created_at.desc(), CrawlTask.id.desc())
        if status is not None:
            statement = statement.where(CrawlTask.status == status)
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def count_pending_task_documents(self, task_id: int) -> int:
        document_ids = (
            select(DataLineage.document_id)
            .where(
                DataLineage.crawl_task_id == task_id,
                DataLineage.document_id.is_not(None),
            )
            .distinct()
        )
        count = await self.session.scalar(
            select(func.count(Document.id)).where(
                Document.id.in_(document_ids),
                Document.final_status.not_in(["approved", "rejected"]),
            )
        )
        return int(count or 0)

    async def recover_stale_tasks(
        self,
        *,
        cutoff: datetime,
        max_recovery_attempts: int,
        limit: int,
    ) -> tuple[list[int], list[int]]:
        result = await self.session.execute(
            select(CrawlTask)
            .where(
                CrawlTask.status.in_(
                    [
                        "running",
                        "calling_coze",
                        "coze_running",
                        "normalizing",
                        "saving_documents",
                    ]
                ),
                CrawlTask.started_at.is_not(None),
                CrawlTask.started_at < cutoff,
            )
            .order_by(CrawlTask.started_at, CrawlTask.id)
            .limit(limit)
        )
        recovered: list[int] = []
        exhausted: list[int] = []
        now = datetime.now(UTC)
        for task in result.scalars():
            if task.retry_count >= max_recovery_attempts:
                task.status = "failed"
                task.current_stage = "failed"
                task.finished_at = now
                task.completed_at = now
                task.failed_count += 1
                task.error_message = "WORKER_LOST_MAX_RECOVERIES"
                task.provider_error_code = "WORKER_LOST_MAX_RECOVERIES"
                task.provider_error_message = "Worker recovery attempts were exhausted"
                exhausted.append(task.id)
                continue
            task.status = "pending"
            task.current_stage = "pending"
            task.started_at = None
            task.finished_at = None
            task.completed_at = None
            task.error_message = "WORKER_LOST_RECOVERED"
            task.provider_status = "recovered_for_retry"
            task.provider_error_code = None
            task.provider_error_message = None
            task.provider_task_id = None
            task.coze_execution_id = None
            task.next_retry_at = None
            task.retry_count += 1
            _reset_progress(task)
            recovered.append(task.id)
        await self.session.commit()
        return recovered, exhausted

    async def list_pending_task_ids(self, *, limit: int) -> list[int]:
        result = await self.session.execute(
            select(CrawlTask.id)
            .where(CrawlTask.status == "pending")
            .order_by(CrawlTask.created_at, CrawlTask.id)
            .limit(limit)
        )
        return list(result.scalars())

    async def save_task(self, task: CrawlTask) -> CrawlTask:
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def lock_source_column(self, source_column_id: int) -> None:
        await self.session.execute(
            select(SourceColumn.id).where(SourceColumn.id == source_column_id).with_for_update()
        )

    async def find_document(
        self,
        *,
        source_column_id: int,
        canonical_url: str,
        lock_for_update: bool = False,
    ) -> Document | None:
        statement = select(Document).where(
            Document.source_column_id == source_column_id,
            Document.canonical_url == canonical_url,
        )
        if lock_for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def add_document(self, document: Document) -> Document:
        self.session.add(document)
        await self.session.flush()
        return document

    async def count_document_versions(self, document_id: int) -> int:
        count = await self.session.scalar(
            select(func.count(DocumentVersion.id)).where(DocumentVersion.document_id == document_id)
        )
        return int(count or 0)

    async def add_document_version(self, version: DocumentVersion) -> DocumentVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def latest_document_review(
        self, document_id: int, review_type: str
    ) -> DocumentReview | None:
        result = await self.session.execute(
            select(DocumentReview)
            .where(
                DocumentReview.document_id == document_id,
                DocumentReview.review_type == review_type,
            )
            .order_by(DocumentReview.created_at.desc(), DocumentReview.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_document_chunks_stale(self, document_id: int) -> None:
        await self.session.execute(
            update(Chunk).where(Chunk.document_id == document_id).values(vector_status="stale")
        )

    async def add_attachment(self, attachment: Attachment) -> Attachment:
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def add_lineage(self, lineage: DataLineage) -> DataLineage:
        self.session.add(lineage)
        await self.session.flush()
        return lineage

    async def ensure_document_lineage(
        self,
        *,
        task_id: int,
        source_id: int,
        document_id: int,
        document_version_id: int | None = None,
    ) -> DataLineage:
        result = await self.session.execute(
            select(DataLineage)
            .where(
                DataLineage.crawl_task_id == task_id,
                DataLineage.document_id == document_id,
            )
            .order_by(DataLineage.id)
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            if document_version_id is not None:
                existing.document_version_id = document_version_id
            return existing
        lineage = DataLineage(
            lineage_id=str(uuid.uuid4()),
            source_id=source_id,
            crawl_task_id=task_id,
            document_id=document_id,
            document_version_id=document_version_id,
        )
        return await self.add_lineage(lineage)

    async def count_unresolved_failures(self, task_id: int) -> int:
        result = await self.session.scalar(
            select(func.count(CrawlTaskFailure.id)).where(
                CrawlTaskFailure.crawl_task_id == task_id,
                CrawlTaskFailure.status.not_in({"succeeded", "skipped"}),
            )
        )
        return int(result or 0)

    async def add_coze_invocation(self, invocation: CozeInvocation) -> CozeInvocation:
        self.session.add(invocation)
        await self.session.flush()
        return invocation

    async def list_coze_invocations(self, task_id: int) -> list[CozeInvocation]:
        result = await self.session.execute(
            select(CozeInvocation)
            .where(CozeInvocation.crawl_task_id == task_id)
            .order_by(CozeInvocation.created_at.desc(), CozeInvocation.id.desc())
        )
        return list(result.scalars())

    async def list_failures(self, task_id: int) -> list[CrawlTaskFailure]:
        result = await self.session.execute(
            select(CrawlTaskFailure)
            .where(CrawlTaskFailure.crawl_task_id == task_id)
            .order_by(CrawlTaskFailure.created_at, CrawlTaskFailure.id)
        )
        return list(result.scalars())

    async def get_failure(self, failure_id: int) -> CrawlTaskFailure | None:
        result = await self.session.execute(
            select(CrawlTaskFailure)
            .where(CrawlTaskFailure.id == failure_id)
            .options(
                selectinload(CrawlTaskFailure.crawl_task)
                .selectinload(CrawlTask.source_column)
                .selectinload(SourceColumn.source)
            )
        )
        return result.scalar_one_or_none()

    async def add_failure(self, failure: CrawlTaskFailure) -> CrawlTaskFailure:
        existing = await self.session.execute(
            select(CrawlTaskFailure).where(
                CrawlTaskFailure.crawl_task_id == failure.crawl_task_id,
                CrawlTaskFailure.url == failure.url,
                CrawlTaskFailure.stage == failure.stage,
                CrawlTaskFailure.error_code == failure.error_code,
            )
        )
        current = existing.scalar_one_or_none()
        if current is not None:
            current.error_message = failure.error_message
            current.retryable = failure.retryable
            if current.status not in {"succeeded", "retrying"}:
                current.status = failure.status
            return current
        self.session.add(failure)
        await self.session.flush()
        return failure

    async def list_task_documents(self, task_id: int) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .join(DataLineage, DataLineage.document_id == Document.id)
            .where(DataLineage.crawl_task_id == task_id)
            .options(selectinload(Document.reviews))
            .order_by(Document.id)
        )
        return list(result.scalars().unique())

    async def acceptance_document_ids(self, task_id: int) -> tuple[list[int], list[str], int]:
        result = await self.session.execute(
            select(Document.id, Document.document_id)
            .join(DataLineage, DataLineage.document_id == Document.id)
            .where(DataLineage.crawl_task_id == task_id)
            .distinct()
            .order_by(Document.id)
        )
        rows = result.all()
        database_ids = [int(row[0]) for row in rows]
        document_ids = [str(row[1]) for row in rows]
        if not database_ids:
            return database_ids, document_ids, 0
        chunk_count = await self.session.scalar(
            select(func.count(Chunk.id)).where(Chunk.document_id.in_(database_ids))
        )
        return database_ids, document_ids, int(chunk_count or 0)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


def _reset_progress(task: CrawlTask) -> None:
    task.discovered_count = 0
    task.fetched_count = 0
    task.success_count = 0
    task.url_duplicate_count = 0
    task.content_duplicate_count = 0
    task.semantic_duplicate_count = 0
    task.failed_count = 0
    task.accepted_count = 0
    task.rejected_count = 0
    task.pending_review_count = 0
