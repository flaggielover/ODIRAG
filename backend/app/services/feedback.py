from __future__ import annotations

from app.errors import ConflictError, NotFoundError
from app.models import EvaluationQuestion, QueryTrace, UserFeedback
from app.repositories.feedback import FeedbackRepository
from app.schemas.feedback import FeedbackCreate

_CONVERTIBLE_TYPES = {
    "not_helpful",
    "incorrect_citation",
    "missing_document",
    "incomplete_answer",
    "should_refuse",
    "should_not_refuse",
}


class FeedbackService:
    def __init__(self, repository: FeedbackRepository) -> None:
        self.repository = repository

    async def create(self, payload: FeedbackCreate) -> UserFeedback:
        if await self.repository.get_trace(payload.trace_id) is None:
            raise NotFoundError("Query trace", payload.trace_id)
        if (
            payload.expected_document_id is not None
            and await self.repository.get_document(payload.expected_document_id) is None
        ):
            raise NotFoundError("Document", payload.expected_document_id)
        feedback = await self.repository.add(
            UserFeedback(
                trace_id=payload.trace_id,
                rating=payload.rating,
                feedback_type=payload.feedback_type,
                comment=payload.comment,
                expected_document_id=payload.expected_document_id,
            )
        )
        await self.repository.commit()
        return await self.repository.refresh(feedback)

    async def list(
        self,
        *,
        resolved: bool | None = None,
        feedback_type: str | None = None,
        converted_to_evaluation: bool | None = None,
        limit: int = 100,
    ) -> list[UserFeedback]:
        return await self.repository.list(
            resolved=resolved,
            feedback_type=feedback_type,
            converted_to_evaluation=converted_to_evaluation,
            limit=limit,
        )

    async def convert_to_evaluation(self, feedback_id: int) -> UserFeedback:
        feedback = await self.repository.get(feedback_id)
        if feedback is None:
            raise NotFoundError("Feedback", feedback_id)
        if feedback.feedback_type not in _CONVERTIBLE_TYPES:
            raise ConflictError("Helpful feedback does not represent a regression case")

        question_id = f"feedback-{feedback.id}"
        existing = await self.repository.get_evaluation_question(question_id)
        if existing is None:
            await self.repository.add_evaluation_question(
                _evaluation_question(feedback, question_id)
            )
        feedback.resolved = True
        feedback.converted_to_evaluation = True
        await self.repository.commit()
        return await self.repository.refresh(feedback)


def _evaluation_question(
    feedback: UserFeedback,
    question_id: str,
) -> EvaluationQuestion:
    trace = feedback.trace
    if trace is None:
        raise RuntimeError("feedback trace relationship was not loaded")
    expected_document_ids = _expected_document_ids(feedback, trace)
    expected_chunk_ids = _expected_chunk_ids(feedback, trace)
    answer_points = (
        [feedback.comment.strip()]
        if feedback.comment
        and feedback.comment.strip()
        and feedback.feedback_type in {"not_helpful", "incomplete_answer"}
        else []
    )
    return EvaluationQuestion(
        question_id=question_id,
        question=trace.user_query,
        query_type=trace.query_type,
        expected_document_ids=expected_document_ids,
        expected_chunk_ids=expected_chunk_ids,
        expected_answer_points=answer_points,
        expected_filters=dict(trace.parsed_filters_json),
        should_refuse=feedback.feedback_type == "should_refuse",
        difficulty="feedback",
        category=f"feedback/{feedback.feedback_type}",
        created_by=f"feedback:{feedback.id}",
        verified=True,
    )


def _expected_document_ids(
    feedback: UserFeedback,
    trace: QueryTrace,
) -> list[str]:
    if feedback.feedback_type == "should_refuse":
        return []
    if feedback.expected_document is not None:
        return [feedback.expected_document.document_id]
    if feedback.feedback_type == "incorrect_citation":
        return []
    return _citation_values(trace, "document_id")


def _expected_chunk_ids(
    feedback: UserFeedback,
    trace: QueryTrace,
) -> list[str]:
    if feedback.feedback_type in {
        "incorrect_citation",
        "missing_document",
        "should_refuse",
        "should_not_refuse",
    }:
        return []
    return _citation_values(trace, "chunk_id")


def _citation_values(trace: QueryTrace, key: str) -> list[str]:
    return list(
        dict.fromkeys(
            str(value)
            for citation in trace.citations_json
            if isinstance(citation, dict)
            and (value := citation.get(key)) is not None
            and str(value)
        )
    )
