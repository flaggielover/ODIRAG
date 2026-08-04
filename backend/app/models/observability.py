from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import (
    JSON_VALUE,
    Base,
    CreatedAtMixin,
    IdMixin,
    JsonObject,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.models.document import Attachment, Chunk, Document, DocumentVersion
    from app.models.evaluation import EvaluationRun
    from app.models.source import CrawlTask, Source


class QueryTrace(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "query_traces"
    __table_args__ = (
        CheckConstraint("latency_ms >= 0", name="latency_ms_nonnegative"),
        CheckConstraint("cost >= 0", name="cost_nonnegative"),
        Index("ix_query_traces_type_created", "query_type", "created_at"),
        Index("ix_query_traces_refusal_created", "refusal", "created_at"),
    )

    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    parsed_filters_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    bm25_results_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    vector_results_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    fusion_results_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    rerank_results_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    final_context_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    prompt_version: Mapped[str | None] = mapped_column(String(64), index=True)
    prompt_snapshot_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict, server_default=text("'{}'")
    )
    model_name: Mapped[str | None] = mapped_column(String(255), index=True)
    answer: Mapped[str | None] = mapped_column(Text)
    citations_json: Mapped[list[dict[str, object]]] = mapped_column(
        JSON_VALUE, nullable=False, default=list
    )
    refusal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    token_usage_json: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=0, server_default="0"
    )

    feedback: Mapped[list[UserFeedback]] = relationship(
        back_populates="trace", cascade="all, delete-orphan", passive_deletes=True
    )


class UserFeedback(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "user_feedback"
    __table_args__ = (
        CheckConstraint("rating IS NULL OR (rating >= 1 AND rating <= 5)", name="rating_range"),
        Index("ix_user_feedback_resolved_created", "resolved", "created_at"),
        Index("ix_user_feedback_type_created", "feedback_type", "created_at"),
    )

    trace_id: Mapped[str] = mapped_column(
        ForeignKey("query_traces.trace_id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[int | None] = mapped_column(Integer)
    feedback_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    expected_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    converted_to_evaluation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )

    trace: Mapped[QueryTrace] = relationship(back_populates="feedback")
    expected_document: Mapped[Document | None] = relationship(
        back_populates="feedback_expectations"
    )


class DataLineage(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "data_lineage"
    __table_args__ = (
        Index("ix_data_lineage_document_chunk", "document_id", "chunk_id"),
        Index("ix_data_lineage_source_crawl", "source_id", "crawl_task_id"),
        Index("ix_data_lineage_evaluation", "evaluation_run_id", "created_at"),
    )

    lineage_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )
    crawl_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL"), index=True
    )
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachments.id", ondelete="SET NULL"), index=True
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), index=True
    )
    vector_point_id: Mapped[str | None] = mapped_column(String(255), index=True)
    evaluation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="SET NULL"), index=True
    )

    source: Mapped[Source | None] = relationship(back_populates="lineage_records")
    crawl_task: Mapped[CrawlTask | None] = relationship(back_populates="lineage_records")
    document: Mapped[Document | None] = relationship(back_populates="lineage_records")
    document_version: Mapped[DocumentVersion | None] = relationship(
        back_populates="lineage_records"
    )
    attachment: Mapped[Attachment | None] = relationship(back_populates="lineage_records")
    chunk: Mapped[Chunk | None] = relationship(back_populates="lineage_records")
    evaluation_run: Mapped[EvaluationRun | None] = relationship(back_populates="lineage_records")


class Alert(IdMixin, TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint("occurrence_count > 0", name="occurrence_count_positive"),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="status_allowed",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'high', 'critical')",
            name="severity_allowed",
        ),
        Index("ix_alerts_status_severity", "status", "severity"),
        Index("ix_alerts_type_last_seen", "alert_type", "last_seen_at"),
    )

    alert_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(
        String(32), nullable=False, default="warning", server_default="warning", index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="open", server_default="open", index=True
    )
    component: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    details_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict, server_default=text("'{}'")
    )
    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
