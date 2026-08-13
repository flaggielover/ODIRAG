from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.models import DocumentMetadataCorrection, DocumentReview
from app.repositories.documents import DocumentRepository
from app.services.filter_config import load_filter_config
from app.services.parsing import AttachmentAuditSummary, ParsingService

_DEFAULT_FILTER_CONFIG = Path(__file__).resolve().parents[3] / "config" / "filters.yaml"


@dataclass(frozen=True, slots=True)
class DataDebtCleanupSummary:
    attachments: AttachmentAuditSummary
    pending_documents_audited: int
    auto_rejected: int
    human_review_required: int
    historical_metadata_observations: int


class DataDebtCleanupService:
    """Idempotently close mechanical data debt without acting as a human reviewer."""

    def __init__(
        self,
        repository: DocumentRepository,
        *,
        filter_config_path: Path = _DEFAULT_FILTER_CONFIG,
    ) -> None:
        self.repository = repository
        self.parsing = ParsingService(repository)
        self.hard_minimum_chars = load_filter_config(filter_config_path).hard_minimum_chars

    async def run(self, *, limit: int = 1000) -> DataDebtCleanupSummary:
        attachment_summary = await self.parsing.audit_pending_attachments(limit=limit)
        reviews_created = 0
        auto_rejected = 0
        pending_documents = await self.repository.list_pending_documents(limit=limit)
        for document in pending_documents:
            if len(document.content.strip()) < self.hard_minimum_chars and not document.attachments:
                if await self.repository.has_review(document.id, "data_debt_hard_reject"):
                    continue
                document.rule_filter_status = "rejected"
                document.llm_review_status = "rejected"
                document.manual_review_status = "not_required"
                document.final_status = "rejected"
                await self.repository.add_review(
                    DocumentReview(
                        document_id=document.id,
                        review_type="data_debt_hard_reject",
                        reviewer="system:phase-g",
                        decision="reject",
                        quality_score=document.quality_score,
                        document_type=document.document_type,
                        topics_json=[],
                        summary="Deterministic hard filter rejected empty or undersized content.",
                        reasons_json=["content_too_short_hard", "no_attachment_evidence"],
                        extracted_fields_json={"content_length": len(document.content)},
                    )
                )
                auto_rejected += 1
                continue
            if await self.repository.has_data_debt_review(document.id):
                continue
            await self.repository.add_review(
                DocumentReview(
                    document_id=document.id,
                    review_type="data_debt_audit",
                    reviewer="system:phase-g",
                    decision="human_review_required",
                    quality_score=document.quality_score,
                    document_type=document.document_type,
                    topics_json=[],
                    summary="Automated checks cannot replace the configured manual approval gate.",
                    reasons_json=["HUMAN_REVIEW_REQUIRED"],
                    extracted_fields_json={
                        "final_status": document.final_status,
                        "manual_review_status": document.manual_review_status,
                    },
                    model_name=None,
                    prompt_name=None,
                    prompt_version=None,
                    raw_response=None,
                )
            )
            reviews_created += 1

        correction_observations = 0
        invalid_region_documents = await self.repository.list_invalid_region_documents(limit=limit)
        for document in invalid_region_documents:
            correction_key = hashlib.sha256(
                f"{document.id}:region:??:historical_invalid_region".encode()
            ).hexdigest()
            created = await self.repository.add_metadata_correction_if_absent(
                DocumentMetadataCorrection(
                    document_id=document.id,
                    field_name="region",
                    old_value="??",
                    new_value=None,
                    status="unresolved",
                    reason="historical_invalid_region_requires_trustworthy_source_evidence",
                    evidence_source="phase_g_data_debt_audit",
                    correction_key=correction_key,
                )
            )
            correction_observations += int(created)

        await self.repository.commit()
        return DataDebtCleanupSummary(
            attachments=attachment_summary,
            pending_documents_audited=len(pending_documents),
            auto_rejected=auto_rejected,
            human_review_required=reviews_created,
            historical_metadata_observations=correction_observations,
        )
