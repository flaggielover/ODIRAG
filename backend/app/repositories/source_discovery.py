from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Document,
    Source,
    SourceCandidate,
    SourceCandidateColumn,
    SourceDiscoveryEvent,
    SourceDiscoveryRun,
)


class SourceDiscoveryRepository:
    """Persistence boundary for discovery runs and their audit trail."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def content_gap(
        self,
        *,
        topic: str,
        region: str | None,
        required_source_count: int,
        required_document_count: int,
    ) -> tuple[int, int, dict[str, Any]]:
        source_statement = (
            select(func.count(func.distinct(Source.id)))
            .join(Document, Document.source_id == Source.id)
            .where(
                Source.enabled.is_(True),
                Document.final_status.in_(["approved", "indexed"]),
            )
        )
        # A disabled source must not satisfy the document side of the gap.  A
        # document left behind by an intentionally retired source is historical
        # data, not active source-pool coverage.
        document_statement = (
            select(func.count(Document.id))
            .join(Source, Document.source_id == Source.id)
            .where(
                Source.enabled.is_(True),
                Document.final_status.in_(["approved", "indexed"]),
            )
        )
        if region:
            source_statement = source_statement.where(Source.region == region)
            document_statement = document_statement.where(Document.region == region)
        phrase = topic.strip()
        escaped_phrase = phrase.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_phrase}%"
        topic_match = or_(
            Document.title.ilike(pattern, escape="\\"),
            Document.content.ilike(pattern, escape="\\"),
        )
        source_statement = source_statement.where(topic_match)
        document_statement = document_statement.where(topic_match)
        source_count = int((await self.session.execute(source_statement)).scalar_one() or 0)
        document_count = int((await self.session.execute(document_statement)).scalar_one() or 0)
        gap_detected = (
            source_count < required_source_count or document_count < required_document_count
        )
        evidence = {
            "topic": phrase,
            "region": region,
            "required_source_count": required_source_count,
            "required_document_count": required_document_count,
            "existing_source_count": source_count,
            "existing_document_count": document_count,
            "gap_detected": gap_detected,
            "matching_source_query": "enabled source with an approved/indexed matching document",
            "matching_document_query": (
                "enabled source document title/content contains the literal topic"
            ),
        }
        return source_count, document_count, evidence

    async def create_run(self, run: SourceDiscoveryRun) -> SourceDiscoveryRun:
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def auto_run_is_due(
        self,
        *,
        topic: str,
        min_interval_seconds: int,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        """Check whether an unattended run may be created for ``topic``.

        The scheduler deliberately scopes this guard to the topic, rather than
        to a region, so a manual run cannot be duplicated by an automatic run
        with a different optional region.  Active work always wins over the
        cooldown; completed, no-gap, and failed runs are rate-limited by their
        creation time.
        """
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be non-negative")

        normalized_topic = topic.strip().casefold()
        if not normalized_topic:
            return False, "empty_topic"

        topic_expression = func.lower(func.trim(SourceDiscoveryRun.topic))
        active_result = await self.session.execute(
            select(SourceDiscoveryRun.id)
            .where(
                topic_expression == normalized_topic,
                SourceDiscoveryRun.status.in_(["pending", "running", "awaiting_approval"]),
            )
            .limit(1)
        )
        if active_result.scalar_one_or_none() is not None:
            return False, "active_run"

        latest_result = await self.session.execute(
            select(SourceDiscoveryRun.created_at)
            .where(topic_expression == normalized_topic)
            .order_by(SourceDiscoveryRun.created_at.desc(), SourceDiscoveryRun.id.desc())
            .limit(1)
        )
        latest_created_at = latest_result.scalar_one_or_none()
        if latest_created_at is None:
            return True, "due"

        if latest_created_at.tzinfo is None:
            latest_created_at = latest_created_at.replace(tzinfo=UTC)
        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)
        if latest_created_at > current_time - timedelta(seconds=min_interval_seconds):
            return False, "cooldown"
        return True, "due"

    async def get_run(self, run_id: int) -> SourceDiscoveryRun | None:
        result = await self.session.execute(
            select(SourceDiscoveryRun)
            .where(SourceDiscoveryRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_runs(self, *, limit: int = 100) -> list[SourceDiscoveryRun]:
        result = await self.session.execute(
            select(SourceDiscoveryRun)
            .execution_options(populate_existing=True)
            .order_by(SourceDiscoveryRun.created_at.desc(), SourceDiscoveryRun.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def claim_run(self, run_id: int) -> SourceDiscoveryRun | None:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(SourceDiscoveryRun)
            .where(SourceDiscoveryRun.id == run_id, SourceDiscoveryRun.status == "pending")
            .values(
                status="running",
                started_at=now,
                finished_at=None,
                error_message=None,
                attempt_count=SourceDiscoveryRun.attempt_count + 1,
            )
        )
        await self.session.commit()
        if getattr(result, "rowcount", 0) != 1:
            return None
        return await self.get_run(run_id)

    async def save_run(self, run: SourceDiscoveryRun) -> SourceDiscoveryRun:
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def create_candidate(self, candidate: SourceCandidate) -> SourceCandidate:
        self.session.add(candidate)
        await self.session.flush()
        return candidate

    async def get_candidate(self, candidate_id: int) -> SourceCandidate | None:
        result = await self.session.execute(
            select(SourceCandidate)
            .where(SourceCandidate.id == candidate_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_candidate_by_url(
        self, *, run_id: int, homepage_url: str
    ) -> SourceCandidate | None:
        result = await self.session.execute(
            select(SourceCandidate)
            .where(
                SourceCandidate.run_id == run_id,
                SourceCandidate.canonical_homepage_url == homepage_url,
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def reset_candidate_for_retry(self, candidate: SourceCandidate) -> SourceCandidate:
        await self.session.execute(
            delete(SourceCandidateColumn).where(SourceCandidateColumn.candidate_id == candidate.id)
        )
        candidate.official_status = "unknown"
        candidate.official_score = None
        candidate.official_evidence_json = {}
        candidate.validation_status_code = None
        candidate.validation_final_url = None
        candidate.status = "discovered"
        candidate.quality_score = None
        candidate.quality_breakdown_json = {}
        candidate.trial_column_count = 0
        candidate.trial_document_count = 0
        candidate.trial_success_count = 0
        candidate.trial_failed_count = 0
        candidate.trial_average_chars = 0
        candidate.rejection_reason = None
        candidate.approved_by = None
        candidate.approved_at = None
        candidate.source_id = None
        await self.session.flush()
        return candidate

    async def list_candidates(self, run_id: int) -> list[SourceCandidate]:
        result = await self.session.execute(
            select(SourceCandidate)
            .execution_options(populate_existing=True)
            .where(SourceCandidate.run_id == run_id)
            .order_by(SourceCandidate.quality_score.desc(), SourceCandidate.id)
        )
        return list(result.scalars())

    async def list_candidate_columns(self, candidate_id: int) -> list[SourceCandidateColumn]:
        result = await self.session.execute(
            select(SourceCandidateColumn)
            .execution_options(populate_existing=True)
            .where(SourceCandidateColumn.candidate_id == candidate_id)
            .order_by(SourceCandidateColumn.quality_score.desc(), SourceCandidateColumn.id)
        )
        return list(result.scalars())

    async def create_column(self, column: SourceCandidateColumn) -> SourceCandidateColumn:
        self.session.add(column)
        await self.session.flush()
        return column

    async def save_candidate(self, candidate: SourceCandidate) -> SourceCandidate:
        await self.session.commit()
        await self.session.refresh(candidate)
        return candidate

    async def save_column(self, column: SourceCandidateColumn) -> SourceCandidateColumn:
        await self.session.commit()
        await self.session.refresh(column)
        return column

    async def add_event(self, event: SourceDiscoveryEvent) -> SourceDiscoveryEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(
        self, *, run_id: int, candidate_id: int | None = None, limit: int = 500
    ) -> list[SourceDiscoveryEvent]:
        statement = (
            select(SourceDiscoveryEvent)
            .where(SourceDiscoveryEvent.run_id == run_id)
            .order_by(SourceDiscoveryEvent.created_at, SourceDiscoveryEvent.id)
            .limit(limit)
        )
        if candidate_id is not None:
            statement = statement.where(SourceDiscoveryEvent.candidate_id == candidate_id)
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def claim_candidate_activation(self, candidate_id: int) -> SourceCandidate | None:
        result = await self.session.execute(
            update(SourceCandidate)
            .where(SourceCandidate.id == candidate_id, SourceCandidate.status == "approved")
            .values(status="activating")
        )
        await self.session.commit()
        if getattr(result, "rowcount", 0) != 1:
            return None
        return await self.get_candidate(candidate_id)

    async def approve_candidate(self, candidate_id: int, reviewer: str) -> SourceCandidate | None:
        result = await self.session.execute(
            update(SourceCandidate)
            .where(SourceCandidate.id == candidate_id, SourceCandidate.status == "pending_approval")
            .values(status="approved", approved_by=reviewer, approved_at=datetime.now(UTC))
        )
        await self.session.commit()
        if getattr(result, "rowcount", 0) != 1:
            return None
        return await self.get_candidate(candidate_id)

    async def reject_candidate(
        self, candidate_id: int, reviewer: str, reason: str
    ) -> SourceCandidate | None:
        result = await self.session.execute(
            update(SourceCandidate)
            .where(
                SourceCandidate.id == candidate_id,
                SourceCandidate.status.in_(["pending_approval", "approved"]),
            )
            .values(
                status="rejected",
                rejection_reason=f"{reviewer}: {reason}",
                approved_by=None,
                approved_at=None,
            )
        )
        await self.session.commit()
        if getattr(result, "rowcount", 0) != 1:
            return None
        return await self.get_candidate(candidate_id)

    async def refresh_run_counts(self, run_id: int) -> SourceDiscoveryRun:
        run = await self.get_run(run_id)
        if run is None:
            raise RuntimeError("source discovery run disappeared")
        candidate_result = await self.session.execute(
            select(SourceCandidate.status, func.count(SourceCandidate.id))
            .where(SourceCandidate.run_id == run_id)
            .group_by(SourceCandidate.status)
        )
        counts = {str(status): int(count) for status, count in candidate_result.all()}
        run.candidate_count = sum(counts.values())
        run.approved_count = counts.get("approved", 0) + counts.get("activated", 0)
        run.activated_count = counts.get("activated", 0)
        return run

    async def metrics(self) -> dict[str, object]:
        run_result = await self.session.execute(
            select(SourceDiscoveryRun.status, func.count(SourceDiscoveryRun.id)).group_by(
                SourceDiscoveryRun.status
            )
        )
        candidate_result = await self.session.execute(
            select(SourceCandidate.status, func.count(SourceCandidate.id)).group_by(
                SourceCandidate.status
            )
        )
        column_result = await self.session.execute(
            select(SourceCandidateColumn.status, func.count(SourceCandidateColumn.id)).group_by(
                SourceCandidateColumn.status
            )
        )
        average = await self.session.execute(select(func.avg(SourceCandidate.quality_score)))
        last_run = await self.session.execute(
            select(SourceDiscoveryRun.created_at)
            .order_by(SourceDiscoveryRun.created_at.desc())
            .limit(1)
        )
        return {
            "run_status_counts": {str(k): int(v) for k, v in run_result.all()},
            "candidate_status_counts": {str(k): int(v) for k, v in candidate_result.all()},
            "column_status_counts": {str(k): int(v) for k, v in column_result.all()},
            "pending_approval_count": int(
                (
                    await self.session.execute(
                        select(func.count(SourceCandidate.id)).where(
                            SourceCandidate.status == "pending_approval"
                        )
                    )
                ).scalar_one()
                or 0
            ),
            "activated_source_count": int(
                (
                    await self.session.execute(
                        select(func.count(SourceCandidate.id)).where(
                            SourceCandidate.status == "activated"
                        )
                    )
                ).scalar_one()
                or 0
            ),
            "average_quality_score": float(average.scalar_one() or Decimal("0")),
            "last_run_at": last_run.scalar_one_or_none(),
        }

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
