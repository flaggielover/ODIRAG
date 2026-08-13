from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_key: str
    name: str
    domain: str
    official_status: str


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version: int
    content_hash: str
    content: str
    metadata_json: dict[str, Any]
    changed_fields_json: list[str]
    created_at: datetime


class DocumentAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    attachment_name: str
    source_url: str
    local_path: str | None
    mime_type: str | None
    file_extension: str | None
    file_type: str
    file_size: int | None
    file_hash: str | None
    download_status: str
    parse_status: str
    parsed_text: str | None
    extracted_text_length: int
    parser: str | None
    page_count: int | None
    requires_ocr: bool
    ocr_status: str
    ocr_provider: str | None
    error_code: str | None
    retryable: bool
    parse_attempted_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    review_type: str
    reviewer: str
    decision: str
    quality_score: Decimal | None
    document_type: str | None
    topics_json: list[str]
    summary: str | None
    reasons_json: list[str]
    extracted_fields_json: dict[str, Any]
    model_name: str | None
    prompt_name: str | None
    prompt_version: str | None
    raw_response: str | None
    created_at: datetime


class DocumentMetadataCorrectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    field_name: str
    old_value: str | None
    new_value: str | None
    status: str
    reason: str
    evidence_source: str | None
    correction_key: str
    created_at: datetime


class DocumentSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: str
    source_id: int | None
    title: str
    source_url: str
    publish_date: date | None
    issuing_authority: str | None
    document_number: str | None
    region: str | None
    city: str | None
    document_type: str | None
    word_count: int
    language: str | None
    quality_score: Decimal | None
    rule_filter_status: str
    llm_review_status: str
    manual_review_status: str
    final_status: str
    index_status: str
    version: int
    last_crawl_time: datetime | None
    created_at: datetime
    updated_at: datetime
    source: DocumentSourceResponse | None = None


class DocumentDetailResponse(DocumentSummaryResponse):
    source_column_id: int | None
    subtitle: str | None
    canonical_url: str | None
    author: str | None
    content: str
    raw_content: str | None
    content_hash: str | None
    simhash: str | None
    parent_document_id: int | None
    duplicate_of_document_id: int | None
    first_crawl_time: datetime | None
    versions: list[DocumentVersionResponse] = Field(default_factory=list)
    attachments: list[DocumentAttachmentResponse] = Field(default_factory=list)
    reviews: list[DocumentReviewResponse] = Field(default_factory=list)
    metadata_corrections: list[DocumentMetadataCorrectionResponse] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=1024)
    subtitle: str | None = Field(default=None, max_length=1024)
    author: str | None = Field(default=None, max_length=255)
    issuing_authority: str | None = Field(default=None, max_length=512)
    document_number: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=128)
    city: str | None = Field(default=None, max_length=128)
    document_type: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=32)


class ChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chunk_id: str
    document_id: int
    attachment_id: int | None
    chunk_index: int
    section_path: str | None
    section_title: str | None
    page_number: int | None
    content: str
    content_hash: str
    char_count: int
    token_count: int
    embedding_model: str | None
    embedding_version: str | None
    vector_status: str
    created_at: datetime
    updated_at: datetime


class IndexDocumentResponse(BaseModel):
    document_id: int
    document_version: int
    chunk_count: int
    cache_hits: int
    embedded_count: int
    embedding_model: str
    embedding_version: str
    estimated_cost: float
    vector_point_ids: list[str]
    bm25_document_count: int
