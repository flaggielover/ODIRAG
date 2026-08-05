from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    CrawlTask,
    DataLineage,
    Document,
    DocumentReview,
    PromptVersion,
    StructuredKnowledge,
)


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_document(self, document_id: int) -> Document | None:
        result = await self.session.execute(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.source))
        )
        return result.scalar_one_or_none()

    async def list_pending(self) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(Document.final_status.in_(["pending", "pending_manual_review", "pending_llm"]))
            .order_by(Document.created_at, Document.id)
        )
        return list(result.scalars())

    async def get_prompt(self, prompt_name: str, version: str) -> PromptVersion | None:
        result = await self.session.execute(
            select(PromptVersion).where(
                PromptVersion.prompt_name == prompt_name,
                PromptVersion.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def activate_prompt(self, prompt: PromptVersion) -> PromptVersion:
        await self.session.execute(
            update(PromptVersion)
            .where(
                PromptVersion.prompt_name == prompt.prompt_name,
                PromptVersion.active.is_(True),
            )
            .values(active=False)
        )
        prompt.active = True
        self.session.add(prompt)
        await self.session.flush()
        return prompt

    async def add_review(self, review: DocumentReview) -> DocumentReview:
        self.session.add(review)
        await self.session.flush()
        return review

    async def add_knowledge(self, knowledge: StructuredKnowledge) -> StructuredKnowledge:
        self.session.add(knowledge)
        await self.session.flush()
        return knowledge

    async def reconcile_crawl_tasks(self, document_id: int) -> None:
        """Update waiting-review task counts and close tasks with no pending documents."""

        task_ids = select(DataLineage.crawl_task_id).where(
            DataLineage.document_id == document_id,
            DataLineage.crawl_task_id.is_not(None),
        )
        result = await self.session.execute(
            select(CrawlTask)
            .where(CrawlTask.id.in_(task_ids), CrawlTask.status == "waiting_review")
            .with_for_update()
        )
        tasks = list(result.scalars())
        for task in tasks:
            document_ids = (
                select(DataLineage.document_id)
                .where(
                    DataLineage.crawl_task_id == task.id,
                    DataLineage.document_id.is_not(None),
                )
                .distinct()
            )
            counts_result = await self.session.execute(
                select(Document.final_status, func.count(Document.id))
                .where(Document.id.in_(document_ids))
                .group_by(Document.final_status)
            )
            counts = {status: int(count) for status, count in counts_result.all()}
            accepted = counts.get("approved", 0)
            rejected = counts.get("rejected", 0)
            total = sum(counts.values())
            pending = max(0, total - accepted - rejected)
            task.accepted_count = accepted
            task.rejected_count = rejected
            task.pending_review_count = pending
            if total > 0 and pending == 0:
                now = datetime.now(UTC)
                task.status = "completed"
                task.current_stage = "completed"
                task.provider_status = "completed"
                task.finished_at = now
                task.completed_at = now
                task.error_message = None
                task.provider_error_code = None
                task.provider_error_message = None
                task.next_retry_at = None

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
