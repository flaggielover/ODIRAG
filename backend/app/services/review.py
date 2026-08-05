from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.errors import NotFoundError
from app.filters import FilterDecision, RuleFilter
from app.llm import LLMOrchestrator, ReviewResult
from app.models import Document, DocumentReview, StructuredKnowledge
from app.providers import ProviderResponseError, ProviderUnavailableError
from app.repositories.reviews import ReviewRepository
from app.schemas.review import ExtractedField
from app.services.prompts import PromptService

ALLOWED_STRUCTURED_FIELDS = {
    "issuing_authority",
    "document_number",
    "policy_target",
    "support_measures",
    "application_conditions",
    "funding_amount",
    "deadline",
    "department",
    "region",
    "industry",
    "contact_information",
    "key_indicators",
}


@dataclass(frozen=True, slots=True)
class ReviewPipelineResult:
    document_id: int
    rule_decision: str
    rule_score: float
    llm_decision: str | None
    final_status: str
    extracted_fields: dict[str, Any]


class ReviewService:
    def __init__(
        self,
        repository: ReviewRepository,
        rule_filter: RuleFilter,
        orchestrator: LLMOrchestrator,
        *,
        prompt_name: str,
        prompt_version: str,
        prompt_content: str,
    ) -> None:
        self.repository = repository
        self.rule_filter = rule_filter
        self.orchestrator = orchestrator
        self.prompt_name = prompt_name
        self.prompt_version = prompt_version
        self.prompt_content = prompt_content

    async def run(self, document_id: int) -> ReviewPipelineResult:
        document = await self._document(document_id)
        official = document.source is not None and document.source.official_status == "official"
        rule_result = self.rule_filter.evaluate(
            title=document.title,
            content=document.content,
            official_source=official,
        )
        document.quality_score = Decimal(str(rule_result.score))
        document.rule_filter_status = rule_result.decision.value
        await self.repository.add_review(
            DocumentReview(
                document_id=document.id,
                review_type="rule",
                reviewer="rule_filter",
                decision=rule_result.decision.value,
                quality_score=Decimal(str(rule_result.score)),
                reasons_json=list(rule_result.reasons),
                extracted_fields_json={},
            )
        )
        if rule_result.decision is FilterDecision.REJECT:
            document.final_status = "rejected"
            await self.repository.reconcile_crawl_tasks(document.id)
            await self.repository.commit()
            return ReviewPipelineResult(
                document.id,
                rule_result.decision.value,
                rule_result.score,
                None,
                document.final_status,
                {},
            )
        await self.repository.commit()
        await PromptService(self.repository).ensure(
            name=self.prompt_name,
            version=self.prompt_version,
            content=self.prompt_content,
            change_description="Initial strict document review schema",
        )
        try:
            llm_result = await self._review_with_retry(document)
        except (ProviderUnavailableError, ProviderResponseError):
            document.llm_review_status = "unavailable"
            document.final_status = "pending_llm"
            await self.repository.commit()
            raise
        extracted = self._validate_extracted_fields(document, llm_result)
        await self.repository.add_review(
            DocumentReview(
                document_id=document.id,
                review_type="llm",
                reviewer=self.orchestrator.model_name,
                decision=llm_result.decision,
                quality_score=Decimal(str(llm_result.quality_score)),
                document_type=llm_result.document_type,
                topics_json=llm_result.topics,
                summary=llm_result.summary,
                reasons_json=llm_result.reasons,
                extracted_fields_json=extracted,
                model_name=self.orchestrator.model_name,
                prompt_name=self.prompt_name,
                prompt_version=self.prompt_version,
                raw_response=llm_result.raw_response or llm_result.model_dump_json(),
            )
        )
        for field_name, field in extracted.items():
            await self.repository.add_knowledge(
                StructuredKnowledge(
                    document_id=document.id,
                    knowledge_type="policy_field",
                    field_name=field_name,
                    field_value_json={
                        "value": field["value"],
                        "evidence_quote": field["evidence_quote"],
                    },
                    confidence=Decimal(str(field["confidence"])),
                    extraction_model=self.orchestrator.model_name,
                    prompt_version=self.prompt_version,
                    verified=False,
                )
            )
        document.llm_review_status = llm_result.decision
        document.document_type = llm_result.document_type or document.document_type
        if llm_result.decision == "reject":
            document.final_status = "rejected"
        elif (
            llm_result.decision == "manual_review" or rule_result.decision is FilterDecision.REVIEW
        ):
            document.final_status = "pending_manual_review"
        else:
            document.final_status = "approved"
        await self.repository.reconcile_crawl_tasks(document.id)
        await self.repository.commit()
        return ReviewPipelineResult(
            document.id,
            rule_result.decision.value,
            rule_result.score,
            llm_result.decision,
            document.final_status,
            extracted,
        )

    async def pending(self) -> list[Document]:
        return await self.repository.list_pending()

    async def manual_decision(
        self,
        document_id: int,
        *,
        decision: str,
        reviewer: str,
        summary: str | None = None,
        reasons: list[str] | None = None,
    ) -> Document:
        if decision not in {"approve", "reject"}:
            raise ValueError("manual decision must be approve or reject")
        document = await self._document(document_id)
        document.manual_review_status = decision
        document.final_status = "approved" if decision == "approve" else "rejected"
        await self.repository.add_review(
            DocumentReview(
                document_id=document.id,
                review_type="manual",
                reviewer=reviewer,
                decision=decision,
                summary=summary,
                reasons_json=reasons or [],
                extracted_fields_json={},
            )
        )
        await self.repository.reconcile_crawl_tasks(document.id)
        await self.repository.commit()
        return document

    async def _document(self, document_id: int) -> Document:
        document = await self.repository.get_document(document_id)
        if document is None:
            raise NotFoundError("Document", document_id)
        return document

    async def _review_with_retry(self, document: Document) -> ReviewResult:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((ProviderUnavailableError, ProviderResponseError)),
            stop=stop_after_attempt(3),
            wait=wait_fixed(0),
            reraise=True,
        ):
            with attempt:
                return await self.orchestrator.review_document(
                    title=document.title,
                    content=document.content,
                    prompt=self.prompt_content,
                )
        raise RuntimeError("review retry loop exited without a result")

    @staticmethod
    def _validate_extracted_fields(document: Document, result: ReviewResult) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for field_name, raw_field in result.extracted_fields.items():
            if field_name not in ALLOWED_STRUCTURED_FIELDS:
                raise ProviderResponseError("llm_review", f"unsupported field: {field_name}")
            try:
                field = ExtractedField.model_validate(raw_field)
            except ValidationError as exc:
                raise ProviderResponseError("llm_review", str(exc)) from exc
            if field.evidence_quote not in document.content:
                raise ProviderResponseError(
                    "llm_review", f"evidence quote is not present for field: {field_name}"
                )
            normalized[field_name] = field.model_dump(mode="json")
        return normalized
