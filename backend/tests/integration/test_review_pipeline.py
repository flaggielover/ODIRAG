from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.filters import RuleFilter
from app.llm.protocols import ReviewResult
from app.models import Document, DocumentReview, PromptVersion, Source, StructuredKnowledge
from app.providers import ProviderResponseError, ProviderUnavailableError
from app.repositories.reviews import ReviewRepository
from app.services.filter_config import load_filter_config
from app.services.review import ReviewService


class RetryThenApproveOrchestrator:
    model_name = "test-review-model"

    def __init__(self) -> None:
        self.calls = 0

    async def review_document(self, *, title: str, content: str, prompt: str) -> ReviewResult:
        del title, prompt
        self.calls += 1
        if self.calls < 3:
            raise ProviderUnavailableError("test_llm", "temporary outage")
        quote = "Sichuan Department of Economy"
        assert quote in content
        return ReviewResult(
            decision="approve",
            quality_score=0.92,
            document_type="policy_notice",
            topics=["software"],
            summary="Supported policy document",
            reasons=[],
            extracted_fields={
                "issuing_authority": {
                    "value": quote,
                    "confidence": 0.97,
                    "evidence_quote": quote,
                }
            },
            raw_response='{"decision":"approve"}',
        )


class InvalidEvidenceOrchestrator(RetryThenApproveOrchestrator):
    async def review_document(self, *, title: str, content: str, prompt: str) -> ReviewResult:
        del title, content, prompt
        return ReviewResult(
            decision="approve",
            quality_score=0.8,
            extracted_fields={
                "funding_amount": {
                    "value": "invented",
                    "confidence": 0.8,
                    "evidence_quote": "not in document",
                }
            },
        )


async def _document(session, *, content: str, source_key: str) -> Document:
    source = Source(
        source_key=source_key,
        name="Official source",
        domain=f"{source_key}.gov",
        homepage_url=f"https://{source_key}.gov/",
        official_status="official",
    )
    document = Document(
        document_id=str(uuid.uuid4()),
        source=source,
        title="Software policy notice",
        source_url=f"https://{source_key}.gov/policy",
        content=content,
        word_count=len(content),
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document


def _service(session, orchestrator) -> ReviewService:
    return ReviewService(
        ReviewRepository(session),
        RuleFilter(load_filter_config(__import__("pathlib").Path("../config/filters.yaml"))),
        orchestrator,
        prompt_name="document_review",
        prompt_version="v1",
        prompt_content="strict prompt",
    )


async def test_review_pipeline_retries_persists_raw_response_and_evidence(app) -> None:
    content = "Sichuan Department of Economy issued a policy support notice. " * 8
    async with app.state.database.session_factory() as session:
        document = await _document(session, content=content, source_key="review-success")
        orchestrator = RetryThenApproveOrchestrator()
        result = await _service(session, orchestrator).run(document.id)
        assert orchestrator.calls == 3
        assert result.final_status == "approved"
        assert result.extracted_fields["issuing_authority"]["evidence_quote"] in content
        assert await session.scalar(select(func.count()).select_from(DocumentReview)) == 2
        assert await session.scalar(select(func.count()).select_from(StructuredKnowledge)) == 1
        assert await session.scalar(select(func.count()).select_from(PromptVersion)) == 1
        llm_review = await session.scalar(
            select(DocumentReview).where(DocumentReview.review_type == "llm")
        )
        assert llm_review is not None
        assert llm_review.raw_response == '{"decision":"approve"}'


async def test_review_pipeline_rejects_unbound_evidence(app) -> None:
    content = "Official policy application support requirements. " * 8
    async with app.state.database.session_factory() as session:
        document = await _document(session, content=content, source_key="review-invalid")
        with pytest.raises(ProviderResponseError, match="evidence quote"):
            await _service(session, InvalidEvidenceOrchestrator()).run(document.id)


async def test_rule_rejection_skips_llm_and_manual_review_changes_status(app) -> None:
    async with app.state.database.session_factory() as session:
        document = await _document(session, content="tiny", source_key="review-rule")
        orchestrator = RetryThenApproveOrchestrator()
        service = _service(session, orchestrator)
        result = await service.run(document.id)
        assert result.final_status == "rejected"
        assert orchestrator.calls == 0
        approved = await service.manual_decision(
            document.id, decision="approve", reviewer="admin", reasons=["verified"]
        )
        assert approved.final_status == "approved"
