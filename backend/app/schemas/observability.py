from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class SourceLineageResponse(BaseModel):
    id: int
    source_key: str
    name: str
    homepage_url: str
    official_status: str


class CrawlTaskLineageResponse(BaseModel):
    id: int
    status: str
    task_type: str
    trigger_type: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class DocumentVersionLineageResponse(BaseModel):
    id: int
    version: int
    content_hash: str
    changed_fields: list[str]
    created_at: datetime


class DocumentLineageResponse(BaseModel):
    id: int
    document_id: str
    title: str
    source_url: str
    version: int


class ChunkLineageResponse(BaseModel):
    id: int
    chunk_id: str
    chunk_index: int
    section_path: str | None
    section_title: str | None
    page_number: int | None
    content_hash: str


class CitationLineageResponse(BaseModel):
    citation: dict[str, Any]
    chunk: ChunkLineageResponse | None
    document: DocumentLineageResponse | None
    document_version: DocumentVersionLineageResponse | None
    crawl_task: CrawlTaskLineageResponse | None
    source: SourceLineageResponse | None
    lineage_ids: list[str]
    complete: bool
    missing_steps: list[str]


class AnswerLineageResponse(BaseModel):
    trace_id: str
    answer: str | None
    prompt_version: str | None
    prompt_snapshot: dict[str, Any]
    citations: list[CitationLineageResponse]


AlertSeverity = Literal["info", "warning", "high", "critical"]
AlertStatus = Literal["open", "acknowledged", "resolved"]


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_key: str
    alert_type: str
    severity: AlertSeverity
    status: AlertStatus
    component: str
    message: str
    observed_value: Decimal | None
    threshold_value: Decimal | None
    details_json: dict[str, Any]
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
