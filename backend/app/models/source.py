from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import JSON_VALUE, Base, CreatedAtMixin, IdMixin, JsonObject, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.observability import DataLineage


class Source(IdMixin, TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("priority >= 0", name="priority_nonnegative"),
        CheckConstraint(
            "crawl_provider IN ('coze', 'local', 'playwright')",
            name="crawl_provider_allowed",
        ),
        CheckConstraint(
            "coze_contract_mode IN ('legacy_single_article', 'batch_crawl')",
            name="coze_contract_mode_allowed",
        ),
        Index("ix_sources_enabled_priority", "enabled", "priority"),
        Index("ix_sources_region_city", "region", "city"),
    )

    source_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    region: Mapped[str | None] = mapped_column(String(128), index=True)
    city: Mapped[str | None] = mapped_column(String(128), index=True)
    organization_level: Mapped[str | None] = mapped_column(String(64))
    organization_type: Mapped[str | None] = mapped_column(String(64))
    official_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="official", server_default="official"
    )
    homepage_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    crawl_frequency: Mapped[str] = mapped_column(
        String(64), nullable=False, default="daily", server_default="daily"
    )
    last_crawl_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    crawl_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="coze", server_default="coze", index=True
    )
    last_coze_status: Mapped[str | None] = mapped_column(String(32))
    last_coze_article_count: Mapped[int | None] = mapped_column(Integer)
    last_coze_error: Mapped[str | None] = mapped_column(Text)
    coze_contract_mode: Mapped[str] = mapped_column(
        String(64), nullable=False, default="batch_crawl", server_default="batch_crawl"
    )
    last_coze_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_crawl_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    columns: Mapped[list[SourceColumn]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )
    documents: Mapped[list[Document]] = relationship(back_populates="source")
    lineage_records: Mapped[list[DataLineage]] = relationship(back_populates="source")


class SourceColumn(IdMixin, TimestampMixin, Base):
    __tablename__ = "source_columns"
    __table_args__ = (
        UniqueConstraint("source_id", "column_key", name="uq_source_columns_source_column_key"),
        CheckConstraint("max_pages > 0", name="max_pages_positive"),
        CheckConstraint(
            "request_interval_seconds >= 0", name="request_interval_seconds_nonnegative"
        ),
        Index("ix_source_columns_source_enabled", "source_id", "enabled"),
    )

    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    column_key: Mapped[str] = mapped_column(String(128), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    parser_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="html", server_default="html"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    max_pages: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    request_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    selectors_json: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    pagination_json: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)

    source: Mapped[Source] = relationship(back_populates="columns")
    crawl_tasks: Mapped[list[CrawlTask]] = relationship(
        back_populates="source_column", cascade="all, delete-orphan", passive_deletes=True
    )
    documents: Mapped[list[Document]] = relationship(back_populates="source_column")


class CrawlTask(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "crawl_tasks"
    __table_args__ = (
        CheckConstraint("discovered_count >= 0", name="discovered_count_nonnegative"),
        CheckConstraint("fetched_count >= 0", name="fetched_count_nonnegative"),
        CheckConstraint("success_count >= 0", name="success_count_nonnegative"),
        CheckConstraint("url_duplicate_count >= 0", name="url_duplicate_count_nonnegative"),
        CheckConstraint("content_duplicate_count >= 0", name="content_duplicate_count_nonnegative"),
        CheckConstraint(
            "semantic_duplicate_count >= 0", name="semantic_duplicate_count_nonnegative"
        ),
        CheckConstraint("failed_count >= 0", name="failed_count_nonnegative"),
        CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        CheckConstraint("accepted_count >= 0", name="accepted_count_nonnegative"),
        CheckConstraint("rejected_count >= 0", name="rejected_count_nonnegative"),
        CheckConstraint("pending_review_count >= 0", name="pending_review_count_nonnegative"),
        CheckConstraint(
            "contract_mode IN ('legacy_single_article', 'batch_crawl')",
            name="contract_mode_allowed",
        ),
        CheckConstraint(
            "crawl_provider IN ('coze', 'local', 'playwright')",
            name="crawl_provider_allowed",
        ),
        CheckConstraint(
            "provider IN ('coze', 'local', 'playwright')",
            name="provider_allowed",
        ),
        CheckConstraint(
            "status IN ('pending', 'queued', 'running', 'calling_coze', 'coze_running', "
            "'normalizing', 'saving_documents', 'waiting_review', 'completed', "
            "'partial_failed', 'failed', 'cancelled')",
            name="status_allowed",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="finish_not_before_start",
        ),
        Index("ix_crawl_tasks_source_status", "source_column_id", "status"),
        Index("ix_crawl_tasks_status_created", "status", "created_at"),
    )

    source_column_id: Mapped[int] = mapped_column(
        ForeignKey("source_columns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="incremental", server_default="incremental"
    )
    trigger_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="manual", server_default="manual"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    fetched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    url_duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    content_duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    semantic_duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
    crawl_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="coze", server_default="coze", index=True
    )
    provider_contract: Mapped[str | None] = mapped_column(String(64))
    provider_task_id: Mapped[str | None] = mapped_column(String(255), index=True)
    provider_status: Mapped[str | None] = mapped_column(String(64))
    provider_error_code: Mapped[str | None] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="coze", server_default="coze", index=True
    )
    contract_mode: Mapped[str] = mapped_column(
        String(64), nullable=False, default="batch_crawl", server_default="batch_crawl"
    )
    current_stage: Mapped[str] = mapped_column(
        String(64), nullable=False, default="pending", server_default="pending", index=True
    )
    provider_error_message: Mapped[str | None] = mapped_column(Text)
    coze_execution_id: Mapped[str | None] = mapped_column(String(255), index=True)
    accepted_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rejected_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    pending_review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_articles: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    source_column: Mapped[SourceColumn] = relationship(back_populates="crawl_tasks")
    lineage_records: Mapped[list[DataLineage]] = relationship(back_populates="crawl_task")
    coze_invocations: Mapped[list[CozeInvocation]] = relationship(
        back_populates="crawl_task", cascade="all, delete-orphan", passive_deletes=True
    )
    failures: Mapped[list[CrawlTaskFailure]] = relationship(
        back_populates="crawl_task", cascade="all, delete-orphan", passive_deletes=True
    )


class CozeInvocation(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "coze_invocations"
    __table_args__ = (
        CheckConstraint("attempt_count > 0", name="attempt_count_positive"),
        CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="duration_nonnegative"),
        Index("ix_coze_invocations_task_created", "crawl_task_id", "created_at"),
        Index("ix_coze_invocations_status_created", "status", "created_at"),
    )

    crawl_task_id: Mapped[int] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contract: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    deployment_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    request_json: Mapped[Any] = mapped_column(JSON_VALUE, nullable=False)
    raw_response_json: Mapped[Any | None] = mapped_column(JSON_VALUE)
    normalized_response_json: Mapped[Any | None] = mapped_column(JSON_VALUE)
    http_status_code: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    token_usage_json: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    crawl_task: Mapped[CrawlTask] = relationship(back_populates="coze_invocations")


class CrawlTaskFailure(IdMixin, TimestampMixin, Base):
    __tablename__ = "crawl_task_failures"
    __table_args__ = (
        UniqueConstraint(
            "crawl_task_id", "url", "stage", "error_code", name="uq_crawl_task_failures_identity"
        ),
        CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        CheckConstraint(
            "status IN ('pending', 'queued', 'retrying', 'succeeded', 'failed', 'skipped')",
            name="status_allowed",
        ),
        Index("ix_crawl_task_failures_task_status", "crawl_task_id", "status"),
        Index("ix_crawl_task_failures_retry", "retryable", "next_retry_at"),
    )

    crawl_task_id: Mapped[int] = mapped_column(
        ForeignKey("crawl_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(4096), nullable=False)
    stage: Mapped[str] = mapped_column(String(128), nullable=False)
    error_code: Mapped[str] = mapped_column(String(128), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    retryable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    crawl_task: Mapped[CrawlTask] = relationship(back_populates="failures")
