from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Alert,
    Chunk,
    CrawlTask,
    DataLineage,
    Document,
    DocumentVersion,
    Experiment,
    QueryTrace,
    Source,
)


@dataclass(frozen=True, slots=True)
class CitationLineageContext:
    chunk: Chunk
    document: Document
    source: Source | None
    document_version: DocumentVersion | None
    crawl_task: CrawlTask | None
    lineage_records: tuple[DataLineage, ...]


@dataclass(frozen=True, slots=True)
class CrawlerAggregate:
    status_counts: dict[str, int]
    discovered_count: int
    fetched_count: int
    success_count: int
    failed_count: int


@dataclass(frozen=True, slots=True)
class KnowledgeAggregate:
    final_status_counts: dict[str, int]
    index_status_counts: dict[str, int]
    chunk_count: int


class ObservabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_trace(self, trace_id: str) -> QueryTrace | None:
        result = await self.session.execute(
            select(QueryTrace).where(QueryTrace.trace_id == trace_id)
        )
        return result.scalar_one_or_none()

    async def citation_lineage(self, chunk_id: str) -> CitationLineageContext | None:
        result = await self.session.execute(
            select(Chunk)
            .where(Chunk.chunk_id == chunk_id)
            .options(selectinload(Chunk.document).selectinload(Document.source))
        )
        chunk = result.scalar_one_or_none()
        if chunk is None:
            return None
        lineages = list(
            await self.session.scalars(
                select(DataLineage)
                .where(DataLineage.document_id == chunk.document_id)
                .order_by(DataLineage.created_at.desc(), DataLineage.id.desc())
            )
        )
        version_id = _first_id(
            lineage.document_version_id
            for lineage in lineages
            if lineage.chunk_id in {None, chunk.id}
        )
        crawl_task_id = _first_id(lineage.crawl_task_id for lineage in lineages)
        version = (
            await self.session.get(DocumentVersion, version_id) if version_id is not None else None
        )
        crawl_task = (
            await self.session.get(CrawlTask, crawl_task_id) if crawl_task_id is not None else None
        )
        return CitationLineageContext(
            chunk=chunk,
            document=chunk.document,
            source=chunk.document.source,
            document_version=version,
            crawl_task=crawl_task,
            lineage_records=tuple(lineages),
        )

    async def crawler_aggregate(self, since: datetime) -> CrawlerAggregate:
        rows = (
            await self.session.execute(
                select(CrawlTask.status, func.count(CrawlTask.id))
                .where(CrawlTask.created_at >= since)
                .group_by(CrawlTask.status)
            )
        ).all()
        totals = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(CrawlTask.discovered_count), 0),
                    func.coalesce(func.sum(CrawlTask.fetched_count), 0),
                    func.coalesce(func.sum(CrawlTask.success_count), 0),
                    func.coalesce(func.sum(CrawlTask.failed_count), 0),
                ).where(CrawlTask.created_at >= since)
            )
        ).one()
        return CrawlerAggregate(
            status_counts={str(status): int(count) for status, count in rows},
            discovered_count=int(totals[0]),
            fetched_count=int(totals[1]),
            success_count=int(totals[2]),
            failed_count=int(totals[3]),
        )

    async def knowledge_aggregate(self) -> KnowledgeAggregate:
        final_rows = (
            await self.session.execute(
                select(Document.final_status, func.count(Document.id)).group_by(
                    Document.final_status
                )
            )
        ).all()
        index_rows = (
            await self.session.execute(
                select(Document.index_status, func.count(Document.id)).group_by(
                    Document.index_status
                )
            )
        ).all()
        chunk_count = await self.session.scalar(select(func.count()).select_from(Chunk))
        return KnowledgeAggregate(
            final_status_counts={str(status): int(count) for status, count in final_rows},
            index_status_counts={str(status): int(count) for status, count in index_rows},
            chunk_count=int(chunk_count or 0),
        )

    async def recent_traces(self, since: datetime) -> list[QueryTrace]:
        result = await self.session.execute(
            select(QueryTrace)
            .where(QueryTrace.created_at >= since)
            .order_by(QueryTrace.created_at.desc())
        )
        return list(result.scalars())

    async def regression_experiment_count(self, since: datetime) -> int:
        value = await self.session.scalar(
            select(func.count())
            .select_from(Experiment)
            .where(
                Experiment.created_at >= since,
                Experiment.status == "completed",
                Experiment.conclusion.like("Regression detected.%"),
            )
        )
        return int(value or 0)

    async def get_alert(self, alert_id: int) -> Alert | None:
        return await self.session.get(Alert, alert_id)

    async def get_alert_by_key(self, alert_key: str) -> Alert | None:
        result = await self.session.execute(select(Alert).where(Alert.alert_key == alert_key))
        return result.scalar_one_or_none()

    async def list_alerts(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        statement = select(Alert)
        if status is not None:
            statement = statement.where(Alert.status == status)
        if severity is not None:
            statement = statement.where(Alert.severity == severity)
        statement = statement.order_by(Alert.last_seen_at.desc(), Alert.id.desc()).limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def open_alerts(self) -> list[Alert]:
        result = await self.session.execute(
            select(Alert).where(Alert.status.in_(("open", "acknowledged")))
        )
        return list(result.scalars())

    async def add_alert(self, alert: Alert) -> Alert:
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def refresh(self, alert: Alert) -> Alert:
        await self.session.refresh(alert)
        return alert

    async def commit(self) -> None:
        await self.session.commit()


def _first_id(values: Iterable[int | None]) -> int | None:
    for value in values:
        if value is not None:
            return int(value)
    return None
