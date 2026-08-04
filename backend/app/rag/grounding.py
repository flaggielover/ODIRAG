from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from app.retrieval.models import RetrievalHit


@dataclass(frozen=True, slots=True)
class Citation:
    document_id: str
    chunk_id: str
    title: str
    source: str
    publication_date: str | None
    url: str
    page: int | None
    quote: str


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    sufficient: bool
    reasons: tuple[str, ...]
    conflicts: tuple[str, ...]
    outdated: tuple[str, ...]
    citations: tuple[Citation, ...]


class GroundingService:
    def __init__(
        self,
        *,
        minimum_hits: int = 1,
        minimum_score: float = 0.0,
        quote_chars: int = 220,
        require_official_source: bool = True,
        refuse_on_conflict: bool = True,
    ) -> None:
        self.minimum_hits = minimum_hits
        self.minimum_score = minimum_score
        self.quote_chars = quote_chars
        self.require_official_source = require_official_source
        self.refuse_on_conflict = refuse_on_conflict

    def assess(self, query: str, hits: list[RetrievalHit]) -> EvidenceDecision:
        eligible = [hit for hit in hits if hit.score >= self.minimum_score and hit.content.strip()]
        reasons: list[str] = []
        if len(eligible) < self.minimum_hits:
            reasons.append("insufficient_retrieved_evidence")
        if (
            self.require_official_source
            and eligible
            and not any(
                str(hit.metadata.get("official_status", "")).lower() == "official"
                for hit in eligible
            )
        ):
            reasons.append("official_source_required")
        if eligible and not any(self._overlap(query, hit.content) for hit in eligible):
            reasons.append("question_not_covered")
        conflicts = tuple(self._detect_conflicts(eligible))
        if conflicts and self.refuse_on_conflict:
            reasons.append("conflicting_evidence")
        outdated, outdated_ids = self._detect_outdated(eligible)
        citations = tuple(
            self._citation(hit) for hit in eligible if hit.chunk_id not in outdated_ids
        )
        return EvidenceDecision(
            not reasons,
            tuple(dict.fromkeys(reasons)),
            conflicts,
            tuple(outdated),
            citations,
        )

    def _citation(self, hit: RetrievalHit) -> Citation:
        quote = re.sub(r"\s+", " ", hit.content).strip()[: self.quote_chars]
        metadata = hit.metadata
        return Citation(
            document_id=hit.document_id,
            chunk_id=hit.chunk_id,
            title=hit.title,
            source=str(metadata.get("source_name", hit.source)),
            publication_date=self._date_string(metadata.get("publish_date")),
            url=hit.source_url,
            page=metadata.get("page_number"),
            quote=quote,
        )

    def _detect_conflicts(self, hits: list[RetrievalHit]) -> list[str]:
        by_policy: dict[str, set[str]] = {}
        for hit in hits:
            policy_key = str(hit.metadata.get("policy_key", hit.title)).strip().lower()
            status = str(hit.metadata.get("policy_status", "")).strip().lower()
            if status:
                by_policy.setdefault(policy_key, set()).add(status)
        return [
            f"conflicting_policy_status:{key}"
            for key, statuses in by_policy.items()
            if len(statuses) > 1
        ]

    def _detect_outdated(self, hits: list[RetrievalHit]) -> tuple[list[str], set[str]]:
        grouped: dict[str, list[tuple[date, RetrievalHit]]] = {}
        for hit in hits:
            policy_key = str(
                hit.metadata.get("document_number") or hit.metadata.get("policy_key") or hit.title
            ).strip()
            published = self._date_value(hit.metadata.get("publish_date"))
            if policy_key and published is not None:
                grouped.setdefault(policy_key, []).append((published, hit))
        messages: list[str] = []
        outdated_ids: set[str] = set()
        for policy_key, entries in grouped.items():
            newest_date = max(published for published, _hit in entries)
            newest = min(
                (hit for published, hit in entries if published == newest_date),
                key=lambda hit: hit.chunk_id,
            )
            for published, hit in entries:
                if published < newest_date:
                    outdated_ids.add(hit.chunk_id)
                    messages.append(
                        f"newer_policy_available:{policy_key}:{hit.chunk_id}:{newest.chunk_id}"
                    )
        return messages, outdated_ids

    @staticmethod
    def _overlap(query: str, content: str) -> bool:
        terms = {term.lower() for term in re.findall(r"[A-Za-z0-9]{2,}", query)}
        for segment in re.findall(r"[\u4e00-\u9fff]+", query):
            if len(segment) == 1:
                terms.add(segment)
            else:
                terms.update(segment[index : index + 2] for index in range(len(segment) - 1))
        lowered = content.lower()
        return not terms or any(term in lowered for term in terms)

    @staticmethod
    def _date_string(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _date_value(value: object) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None
