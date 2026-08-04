from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document, DocumentReview, PromptVersion, StructuredKnowledge


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

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
