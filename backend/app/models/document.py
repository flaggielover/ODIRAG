from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import JSON_VALUE, Base, CreatedAtMixin, IdMixin, JsonObject, TimestampMixin

if TYPE_CHECKING:
    from app.models.observability import DataLineage, UserFeedback
    from app.models.source import Source, SourceColumn


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "source_column_id",
            "canonical_url",
            name="uq_documents_source_column_canonical_url",
        ),
        CheckConstraint("word_count >= 0", name="word_count_nonnegative"),
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="quality_score_range",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "last_crawl_time IS NULL OR first_crawl_time IS NULL "
            "OR last_crawl_time >= first_crawl_time",
            name="last_crawl_not_before_first",
        ),
        Index("ix_documents_source_publish_date", "source_id", "publish_date"),
        Index("ix_documents_region_type", "region", "document_type"),
        Index("ix_documents_final_index_status", "final_status", "index_status"),
        Index("ix_documents_review_statuses", "rule_filter_status", "llm_review_status"),
    )

    document_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), index=True
    )
    source_column_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_columns.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(1024))
    source_url: Mapped[str] = mapped_column(String(4096), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(4096), index=True)
    publish_date: Mapped[date | None] = mapped_column(Date, index=True)
    author: Mapped[str | None] = mapped_column(String(255))
    issuing_authority: Mapped[str | None] = mapped_column(String(512), index=True)
    document_number: Mapped[str | None] = mapped_column(String(255), index=True)
    region: Mapped[str | None] = mapped_column(String(128), index=True)
    city: Mapped[str | None] = mapped_column(String(128), index=True)
    document_type: Mapped[str | None] = mapped_column(String(128), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_content: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    simhash: Mapped[str | None] = mapped_column(String(32), index=True)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    language: Mapped[str | None] = mapped_column(String(32), index=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    rule_filter_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    llm_review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    manual_review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    final_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    index_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    parent_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    duplicate_of_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    first_crawl_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_crawl_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source | None] = relationship(back_populates="documents")
    source_column: Mapped[SourceColumn | None] = relationship(back_populates="documents")
    parent_document: Mapped[Document | None] = relationship(
        back_populates="child_documents",
        foreign_keys="Document.parent_document_id",
        remote_side="Document.id",
    )
    child_documents: Mapped[list[Document]] = relationship(
        back_populates="parent_document", foreign_keys="Document.parent_document_id"
    )
    duplicate_of_document: Mapped[Document | None] = relationship(
        back_populates="duplicate_documents",
        foreign_keys="Document.duplicate_of_document_id",
        remote_side="Document.id",
    )
    duplicate_documents: Mapped[list[Document]] = relationship(
        back_populates="duplicate_of_document", foreign_keys="Document.duplicate_of_document_id"
    )
    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    reviews: Mapped[list[DocumentReview]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    metadata_corrections: Mapped[list[DocumentMetadataCorrection]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    structured_knowledge: Mapped[list[StructuredKnowledge]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    feedback_expectations: Mapped[list[UserFeedback]] = relationship(
        back_populates="expected_document"
    )
    lineage_records: Mapped[list[DataLineage]] = relationship(back_populates="document")


class DocumentVersion(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_versions_document_version"),
        CheckConstraint("version > 0", name="version_positive"),
        Index("ix_document_versions_document_created", "document_id", "created_at"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[JsonObject] = mapped_column(JSON_VALUE, nullable=False, default=dict)
    changed_fields_json: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)

    document: Mapped[Document] = relationship(back_populates="versions")
    lineage_records: Mapped[list[DataLineage]] = relationship(back_populates="document_version")


class Attachment(IdMixin, TimestampMixin, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("file_size IS NULL OR file_size >= 0", name="file_size_nonnegative"),
        CheckConstraint("page_count IS NULL OR page_count >= 0", name="page_count_nonnegative"),
        CheckConstraint("extracted_text_length >= 0", name="extracted_text_length_nonnegative"),
        CheckConstraint(
            "ocr_page_count IS NULL OR ocr_page_count >= 0", name="ocr_page_count_nonnegative"
        ),
        CheckConstraint(
            "ocr_text_length IS NULL OR ocr_text_length >= 0", name="ocr_text_length_nonnegative"
        ),
        CheckConstraint(
            "ocr_latency_ms IS NULL OR ocr_latency_ms >= 0", name="ocr_latency_ms_nonnegative"
        ),
        Index("ix_attachments_document_download", "document_id", "download_status"),
        Index("ix_attachments_document_parse", "document_id", "parse_status"),
        Index("ix_attachments_ocr_status", "ocr_status"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attachment_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_url: Mapped[str] = mapped_column(String(4096), nullable=False)
    local_path: Mapped[str | None] = mapped_column(String(4096))
    mime_type: Mapped[str | None] = mapped_column(String(255), index=True)
    file_extension: Mapped[str | None] = mapped_column(String(32), index=True)
    file_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown", index=True
    )
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    file_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    download_http_status: Mapped[int | None] = mapped_column(Integer)
    download_final_url: Mapped[str | None] = mapped_column(String(4096))
    download_error_code: Mapped[str | None] = mapped_column(String(64), index=True)
    download_retryable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    download_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    parse_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )
    parsed_text: Mapped[str | None] = mapped_column(Text)
    extracted_text_length: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    parser: Mapped[str | None] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(64))
    extraction_method: Mapped[str | None] = mapped_column(String(64))
    type_detection_source: Mapped[str | None] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)
    requires_ocr: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ocr_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_required", server_default="not_required"
    )
    ocr_provider: Mapped[str | None] = mapped_column(String(64))
    ocr_version: Mapped[str | None] = mapped_column(String(64))
    ocr_page_count: Mapped[int | None] = mapped_column(Integer)
    ocr_text_length: Mapped[int | None] = mapped_column(Integer)
    ocr_latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64), index=True)
    retryable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    parse_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="attachments")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="attachment")
    lineage_records: Mapped[list[DataLineage]] = relationship(back_populates="attachment")


class DocumentReview(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "document_reviews"
    __table_args__ = (
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="quality_score_range",
        ),
        Index(
            "ix_document_reviews_document_type_created", "document_id", "review_type", "created_at"
        ),
        Index("ix_document_reviews_decision_created", "decision", "created_at"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    document_type: Mapped[str | None] = mapped_column(String(128))
    topics_json: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    reasons_json: Mapped[list[str]] = mapped_column(JSON_VALUE, nullable=False, default=list)
    extracted_fields_json: Mapped[JsonObject] = mapped_column(
        JSON_VALUE, nullable=False, default=dict
    )
    model_name: Mapped[str | None] = mapped_column(String(255))
    prompt_name: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    raw_response: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="reviews")


class DocumentMetadataCorrection(IdMixin, CreatedAtMixin, Base):
    """Immutable audit record for historical metadata observations/corrections.

    A record may be ``unresolved`` when the original value is known to be bad but
    no trustworthy replacement has been established.  The cleanup job never
    mutates the document directly; applied corrections must go through the
    versioning service and retain this audit record.
    """

    __tablename__ = "document_metadata_corrections"
    __table_args__ = (
        UniqueConstraint("correction_key", name="uq_document_metadata_corrections_key"),
        CheckConstraint("status IN ('unresolved', 'applied', 'rejected')", name="status_valid"),
        Index("ix_document_metadata_corrections_document", "document_id"),
        Index("ix_document_metadata_corrections_status", "status"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unresolved", server_default="unresolved"
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_source: Mapped[str | None] = mapped_column(String(1024))
    correction_key: Mapped[str] = mapped_column(String(128), nullable=False)

    document: Mapped[Document] = relationship(back_populates="metadata_corrections")


class Chunk(IdMixin, TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_chunk_index"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_nonnegative"),
        CheckConstraint("page_number IS NULL OR page_number > 0", name="page_number_positive"),
        CheckConstraint("char_count >= 0", name="char_count_nonnegative"),
        CheckConstraint("token_count >= 0", name="token_count_nonnegative"),
        Index("ix_chunks_document_vector_status", "document_id", "vector_status"),
        Index("ix_chunks_attachment_chunk_index", "attachment_id", "chunk_index"),
    )

    chunk_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachments.id", ondelete="SET NULL"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[str | None] = mapped_column(String(2048))
    section_title: Mapped[str | None] = mapped_column(String(1024))
    page_number: Mapped[int | None] = mapped_column(Integer, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    embedding_model: Mapped[str | None] = mapped_column(String(255), index=True)
    embedding_version: Mapped[str | None] = mapped_column(String(64))
    vector_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending", index=True
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
    attachment: Mapped[Attachment | None] = relationship(back_populates="chunks")
    knowledge_evidence: Mapped[list[StructuredKnowledge]] = relationship(
        back_populates="evidence_chunk"
    )
    lineage_records: Mapped[list[DataLineage]] = relationship(back_populates="chunk")


class StructuredKnowledge(IdMixin, TimestampMixin, Base):
    __tablename__ = "structured_knowledge"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        Index("ix_structured_knowledge_document_type", "document_id", "knowledge_type"),
        Index("ix_structured_knowledge_field", "field_name", "verified"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    field_value_json: Mapped[Any] = mapped_column(JSON_VALUE, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    evidence_chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), index=True
    )
    extraction_model: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false"), index=True
    )

    document: Mapped[Document] = relationship(back_populates="structured_knowledge")
    evidence_chunk: Mapped[Chunk | None] = relationship(back_populates="knowledge_evidence")
