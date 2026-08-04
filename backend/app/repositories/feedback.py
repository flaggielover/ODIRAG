from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document, EvaluationQuestion, QueryTrace, UserFeedback


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_trace(self, trace_id: str) -> QueryTrace | None:
        result = await self.session.execute(
            select(QueryTrace).where(QueryTrace.trace_id == trace_id)
        )
        return result.scalar_one_or_none()

    async def get_document(self, document_id: int) -> Document | None:
        return await self.session.get(Document, document_id)

    async def add(self, feedback: UserFeedback) -> UserFeedback:
        self.session.add(feedback)
        await self.session.flush()
        return feedback

    async def get(self, feedback_id: int) -> UserFeedback | None:
        result = await self.session.execute(
            select(UserFeedback)
            .where(UserFeedback.id == feedback_id)
            .options(
                selectinload(UserFeedback.trace),
                selectinload(UserFeedback.expected_document),
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        resolved: bool | None = None,
        feedback_type: str | None = None,
        converted_to_evaluation: bool | None = None,
        limit: int = 100,
    ) -> list[UserFeedback]:
        statement = select(UserFeedback)
        if resolved is not None:
            statement = statement.where(UserFeedback.resolved.is_(resolved))
        if feedback_type is not None:
            statement = statement.where(UserFeedback.feedback_type == feedback_type)
        if converted_to_evaluation is not None:
            statement = statement.where(
                UserFeedback.converted_to_evaluation.is_(converted_to_evaluation)
            )
        result = await self.session.execute(
            statement.order_by(UserFeedback.created_at.desc(), UserFeedback.id.desc()).limit(limit)
        )
        return list(result.scalars())

    async def get_evaluation_question(self, question_id: str) -> EvaluationQuestion | None:
        result = await self.session.execute(
            select(EvaluationQuestion).where(EvaluationQuestion.question_id == question_id)
        )
        return result.scalar_one_or_none()

    async def add_evaluation_question(self, question: EvaluationQuestion) -> EvaluationQuestion:
        self.session.add(question)
        await self.session.flush()
        return question

    async def commit(self) -> None:
        await self.session.commit()

    async def refresh(self, feedback: UserFeedback) -> UserFeedback:
        await self.session.refresh(feedback)
        return feedback
