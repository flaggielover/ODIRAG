from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import JSON_VALUE, Base, IdMixin, JsonObject, TimestampMixin


class SourceDiscoveryRun(IdMixin, TimestampMixin, Base):
    """Durable orchestration record for content-gap driven source discovery."""

    __tablename__ = "source_discovery_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'no_gap', 'awaiting_approval', "
            "'activated', 'failed')",
            name="source_discovery_run_status_allowed",
        ),
        CheckConstraint(
            "required_source_count > 0", name="source_discovery_required_sources_positive"
        ),
        CheckConstraint(
            "required_document_count >= 0",
            name="source_discovery_required_documents_nonnegative",
        ),
        CheckConstraint("max_candidates > 0", name="source_discovery_max_candidates_positive"),
        CheckConstraint("attempt_count >= 0", name="source_discovery_attempt_nonnegative"),
        Index("ix_source_discovery_runs_status_created", "status", "created_at"),
        Index("ix_source_discovery_runs_topic_region", "topic", "region"),
    )

    topic: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    region: Mapped[str | None] = mapped_column(String(128), index=True)
    organization_level: Mapped[str | None] = mapped_column(String(64), index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    required_source_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    required_document_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    existing_source_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    existing_document_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    gap_detected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )
    gap_evidence_json: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    discovery_provider: Mapped[str] = mapped_column(
        String(64), nullable=False, default="brave", server_default="brave"
    )
    max_candidates: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    approved_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    activated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(255), index=True)


class SourceCandidate(IdMixin, TimestampMixin, Base):
    """A candidate discovered from an external search provider."""

    __tablename__ = "source_candidates"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "canonical_homepage_url",
            name="uq_source_candidates_run_homepage",
        ),
        CheckConstraint(
            "official_score IS NULL OR (official_score >= 0 AND official_score <= 1)",
            name="source_candidate_official_score_range",
        ),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="source_candidate_quality_score_range",
        ),
        CheckConstraint(
            "status IN ('discovered', 'validation_failed', 'validated', "
            "'columns_discovered', 'trial_crawled', 'pending_approval', "
            "'approved', 'rejected', 'activating', 'activated', 'failed')",
            name="source_candidate_status_allowed",
        ),
        Index("ix_source_candidates_run_status", "run_id", "status"),
        Index("ix_source_candidates_quality", "quality_score"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("source_discovery_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canonical_homepage_url: Mapped[str] = mapped_column(String(4096), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text)
    search_rank: Mapped[int | None] = mapped_column(Integer)
    discovery_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    discovery_query: Mapped[str] = mapped_column(Text, nullable=False)
    official_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown", index=True
    )
    official_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    official_evidence_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    validation_status_code: Mapped[int | None] = mapped_column(Integer)
    validation_final_url: Mapped[str | None] = mapped_column(String(4096))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="discovered", server_default="discovered", index=True
    )
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    quality_breakdown_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    trial_column_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trial_document_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trial_success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trial_failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trial_average_chars: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )


class SourceCandidateColumn(IdMixin, TimestampMixin, Base):
    """A same-site content column discovered during candidate inspection."""

    __tablename__ = "source_candidate_columns"
    __table_args__ = (
        UniqueConstraint("candidate_id", "column_url", name="uq_source_candidate_columns_url"),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="source_candidate_column_quality_range",
        ),
        Index("ix_source_candidate_columns_candidate_status", "candidate_id", "status"),
    )

    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("source_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    column_key: Mapped[str] = mapped_column(String(128), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_url: Mapped[str] = mapped_column(String(4096), nullable=False)
    parser_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="html", server_default="html"
    )
    selectors_json: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    pagination_json: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    discovery_evidence_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="discovered", server_default="discovered", index=True
    )
    trial_discovered_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trial_fetched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trial_success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trial_failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    trial_average_chars: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    error_message: Mapped[str | None] = mapped_column(Text)


class SourceDiscoveryEvent(IdMixin, Base):
    """Append-only stage transition evidence for audit and monitoring."""

    __tablename__ = "source_discovery_events"
    __table_args__ = (
        Index("ix_source_discovery_events_run_created", "run_id", "created_at"),
        Index("ix_source_discovery_events_candidate_created", "candidate_id", "created_at"),
        Index("ix_source_discovery_events_stage", "stage", "created_at"),
    )

    run_id: Mapped[int] = mapped_column(
        ForeignKey("source_discovery_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_candidates.id", ondelete="CASCADE"), index=True
    )
    # The compound stage/created_at index above covers stage lookups without a
    # second index using the same generated name.
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
