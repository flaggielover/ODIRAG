from __future__ import annotations

import json
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

from app.models import EvaluationQuestion

VALID_VERDICTS: Final[frozenset[str]] = frozenset({"PASS", "FIX", "REJECT"})
REVIEW_STATUS_PARTIAL: Final[str] = "PARTIAL_HUMAN_REVIEW"
REVIEW_STATUS_COMPLETE: Final[str] = "HUMAN_REVIEW_COMPLETE"

WORKBOOK_COLUMNS: Final[tuple[str, ...]] = (
    "id",
    "category",
    "difficulty",
    "question",
    "expected_answer",
    "expected_document_ids",
    "expected_source_urls",
    "expected_chunk_ids",
    "evidence_excerpt",
    "source_title",
    "document_title",
    "region",
    "temporal_constraint",
    "should_refuse",
    "human_verdict",
    "human_corrected_answer",
    "human_corrected_should_refuse",
    "human_additional_chunk_ids",
    "human_notes",
    "reviewed_at",
)


@dataclass(frozen=True, slots=True)
class HumanReviewRow:
    id: str
    category: str
    difficulty: str
    question: str
    expected_answer: str
    expected_document_ids: tuple[str, ...]
    expected_source_urls: tuple[str, ...]
    expected_chunk_ids: tuple[str, ...]
    evidence_excerpt: str
    source_title: str
    document_title: str
    region: str | None
    temporal_constraint: str | None
    should_refuse: bool
    human_verdict: str | None = None
    human_corrected_answer: str | None = None
    human_corrected_should_refuse: bool | None = None
    human_additional_chunk_ids: tuple[str, ...] = ()
    human_notes: str | None = None
    reviewed_at: datetime | None = None

    @property
    def reviewed(self) -> bool:
        return self.human_verdict in VALID_VERDICTS

    @property
    def effective_answer(self) -> str:
        if self.human_verdict == "FIX" and self.human_corrected_answer:
            return self.human_corrected_answer
        return self.expected_answer

    @property
    def effective_should_refuse(self) -> bool:
        if self.human_verdict == "FIX" and self.human_corrected_should_refuse is not None:
            return self.human_corrected_should_refuse
        return self.should_refuse

    @property
    def effective_chunk_ids(self) -> tuple[str, ...]:
        return _unique((*self.expected_chunk_ids, *self.human_additional_chunk_ids))

    @property
    def verified(self) -> bool:
        return self.human_verdict == "PASS" or (
            self.human_verdict == "FIX" and bool(self.human_corrected_answer)
        )


@dataclass(frozen=True, slots=True)
class TraceabilityIndex:
    document_urls: Mapping[str, str]
    chunk_documents: Mapping[str, str]
    chunk_contents: Mapping[str, str]
    document_titles: Mapping[str, str]
    source_titles: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ReviewValidation:
    rows: tuple[HumanReviewRow, ...]
    errors: tuple[str, ...]

    @property
    def counts(self) -> dict[str, int]:
        verdicts = Counter(row.human_verdict for row in self.rows if row.human_verdict)
        return {
            "TOTAL": len(self.rows),
            "REVIEWED": sum(row.reviewed for row in self.rows),
            "UNREVIEWED": sum(not row.reviewed for row in self.rows),
            "PASS": verdicts["PASS"],
            "FIX": verdicts["FIX"],
            "REJECT": verdicts["REJECT"],
            "VERIFIED": sum(row.verified for row in self.rows),
            "TRACEABILITY_ERRORS": len(self.errors),
        }

    @property
    def status(self) -> str:
        counts = self.counts
        if not self.errors and counts["TOTAL"] > 0 and counts["UNREVIEWED"] == 0:
            return REVIEW_STATUS_COMPLETE
        return REVIEW_STATUS_PARTIAL


@dataclass(frozen=True, slots=True)
class ReviewExecution:
    status: str
    applied: bool
    final_output_written: bool
    counts: Mapping[str, int]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "mode": "apply" if self.applied else "dry-run",
            **self.counts,
            "final_output_written": self.final_output_written,
            "errors": list(self.errors),
        }


def parse_review_rows(records: Iterable[Mapping[str, object]]) -> tuple[HumanReviewRow, ...]:
    return tuple(_parse_row(record) for record in records)


def validate_review_rows(
    rows: Iterable[HumanReviewRow], traceability: TraceabilityIndex
) -> ReviewValidation:
    normalized_rows = tuple(rows)
    errors: list[str] = []
    identifiers = Counter(row.id for row in normalized_rows)
    for identifier, count in sorted(identifiers.items()):
        if count > 1:
            errors.append(f"DUPLICATE_ID:{identifier}")
    for row in normalized_rows:
        if not row.id:
            errors.append("MISSING_ID")
            continue
        if row.human_verdict is not None and row.human_verdict not in VALID_VERDICTS:
            errors.append(f"INVALID_VERDICT:{row.id}")
        if row.human_verdict == "FIX" and not row.human_corrected_answer:
            errors.append(f"FIX_REQUIRES_CORRECTED_ANSWER:{row.id}")
        expected_excerpt = _evidence_excerpt_for(row, traceability)
        if expected_excerpt and row.evidence_excerpt != expected_excerpt:
            errors.append(f"EVIDENCE_EXCERPT_MISMATCH:{row.id}")
        expected_document_title = _joined_titles(
            row.expected_document_ids, traceability.document_titles
        )
        if expected_document_title and row.document_title != expected_document_title:
            errors.append(f"DOCUMENT_TITLE_MISMATCH:{row.id}")
        expected_source_title = _joined_titles(
            row.expected_document_ids, traceability.source_titles
        )
        if expected_source_title and row.source_title != expected_source_title:
            errors.append(f"SOURCE_TITLE_MISMATCH:{row.id}")
        _validate_traceability(row, traceability, errors)
    return ReviewValidation(rows=normalized_rows, errors=tuple(_unique(errors)))


async def execute_human_review(
    validation: ReviewValidation,
    *,
    apply: bool,
    output_path: Path,
    persist: Callable[[tuple[EvaluationQuestion, ...]], Awaitable[None]],
    reviewed_at: datetime | None = None,
) -> ReviewExecution:
    if validation.errors:
        return ReviewExecution(
            status=validation.status,
            applied=False,
            final_output_written=False,
            counts=validation.counts,
            errors=validation.errors,
        )
    if not apply:
        return ReviewExecution(
            status=validation.status,
            applied=False,
            final_output_written=False,
            counts=validation.counts,
            errors=(),
        )

    stamp = reviewed_at or datetime.now(UTC)
    applied_rows = tuple(
        replace(row, reviewed_at=row.reviewed_at or stamp) if row.reviewed else row
        for row in validation.rows
    )
    await persist(tuple(_evaluation_question(row) for row in applied_rows))
    output_written = False
    if validation.status == REVIEW_STATUS_COMPLETE:
        _write_verified_output(output_path, applied_rows)
        output_written = True
    return ReviewExecution(
        status=validation.status,
        applied=True,
        final_output_written=output_written,
        counts=validation.counts,
        errors=(),
    )


def _parse_row(record: Mapping[str, object]) -> HumanReviewRow:
    missing = [column for column in WORKBOOK_COLUMNS if column not in record]
    if missing:
        raise ValueError(f"missing workbook columns: {', '.join(missing)}")
    verdict = _optional_text(record["human_verdict"])
    if verdict is not None:
        verdict = verdict.upper()
    return HumanReviewRow(
        id=_text(record["id"]),
        category=_text(record["category"]),
        difficulty=_text(record["difficulty"]),
        question=_text(record["question"]),
        expected_answer=_text(record["expected_answer"]),
        expected_document_ids=_list_cell(record["expected_document_ids"]),
        expected_source_urls=_list_cell(record["expected_source_urls"]),
        expected_chunk_ids=_list_cell(record["expected_chunk_ids"]),
        evidence_excerpt=_text(record["evidence_excerpt"]),
        source_title=_text(record["source_title"]),
        document_title=_text(record["document_title"]),
        region=_optional_text(record["region"]),
        temporal_constraint=_optional_text(record["temporal_constraint"]),
        should_refuse=_required_bool(record["should_refuse"], "should_refuse"),
        human_verdict=verdict,
        human_corrected_answer=_optional_text(record["human_corrected_answer"]),
        human_corrected_should_refuse=_optional_bool(
            record["human_corrected_should_refuse"], "human_corrected_should_refuse"
        ),
        human_additional_chunk_ids=_list_cell(record["human_additional_chunk_ids"]),
        human_notes=_optional_text(record["human_notes"]),
        reviewed_at=_optional_datetime(record["reviewed_at"]),
    )


def _validate_traceability(
    row: HumanReviewRow, traceability: TraceabilityIndex, errors: list[str]
) -> None:
    document_ids = set(row.expected_document_ids)
    for document_id in row.expected_document_ids:
        url = traceability.document_urls.get(document_id)
        if url is None:
            errors.append(f"UNKNOWN_DOCUMENT:{row.id}:{document_id}")
        elif row.expected_source_urls and url not in row.expected_source_urls:
            errors.append(f"SOURCE_URL_MISMATCH:{row.id}:{document_id}")
    for chunk_id in row.effective_chunk_ids:
        chunk_document_id = traceability.chunk_documents.get(chunk_id)
        if chunk_document_id is None:
            errors.append(f"UNKNOWN_CHUNK:{row.id}:{chunk_id}")
        elif chunk_document_id not in document_ids:
            errors.append(f"CHUNK_DOCUMENT_MISMATCH:{row.id}:{chunk_id}")
    if not row.effective_should_refuse:
        if not row.expected_document_ids:
            errors.append(f"POSITIVE_CASE_MISSING_DOCUMENT:{row.id}")
        if not row.expected_source_urls:
            errors.append(f"POSITIVE_CASE_MISSING_SOURCE:{row.id}")
        if not row.effective_chunk_ids:
            errors.append(f"POSITIVE_CASE_MISSING_CHUNK:{row.id}")
        if not row.evidence_excerpt:
            errors.append(f"POSITIVE_CASE_MISSING_EVIDENCE:{row.id}")


def _evaluation_question(row: HumanReviewRow) -> EvaluationQuestion:
    # Source URLs and the publication date are evidence/provenance fields. They
    # are intentionally not passed as retrieval filters: the query analyzer only
    # supports metadata filters declared by the retrieval contract, and applying
    # the expected source would leak the answer into the measured retrieval.
    expected_filters = {"region": row.region} if row.region else {}
    return EvaluationQuestion(
        question_id=row.id,
        question=row.question,
        query_type="rag",
        expected_document_ids=list(row.expected_document_ids),
        expected_chunk_ids=list(row.effective_chunk_ids),
        expected_answer_points=[row.effective_answer] if row.effective_answer else [],
        expected_filters=expected_filters,
        should_refuse=row.effective_should_refuse,
        difficulty=row.difficulty,
        category=row.category,
        created_by="human-evaluation-review",
        verified=row.verified,
    )


def _evidence_excerpt_for(row: HumanReviewRow, traceability: TraceabilityIndex) -> str:
    excerpts = [
        _compact_excerpt(traceability.chunk_contents[chunk_id])
        for chunk_id in row.expected_chunk_ids
        if chunk_id in traceability.chunk_contents
    ]
    return "\n\n".join(excerpts)


def _compact_excerpt(content: str, limit: int = 500) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rsplit(" ", 1)[0] or normalized[:limit]


def _joined_titles(document_ids: tuple[str, ...], titles: Mapping[str, str]) -> str:
    return " | ".join(titles[item] for item in document_ids if item in titles)


def _write_verified_output(path: Path, rows: tuple[HumanReviewRow, ...]) -> None:
    payload = {
        "schema_version": 1,
        "status": REVIEW_STATUS_COMPLETE,
        "question_count": len(rows),
        "human_verified_count": sum(row.verified for row in rows),
        "reviewed_count": sum(row.reviewed for row in rows),
        "questions": [
            {
                "question_id": row.id,
                "question": row.question,
                "query_type": "rag",
                "expected_answer": row.effective_answer,
                "expected_document_ids": list(row.expected_document_ids),
                "expected_source_urls": list(row.expected_source_urls),
                "expected_chunk_ids": list(row.effective_chunk_ids),
                "evidence_excerpt": row.evidence_excerpt,
                "should_refuse": row.effective_should_refuse,
                "difficulty": row.difficulty,
                "category": row.category,
                "human_verdict": row.human_verdict,
                "human_notes": row.human_notes,
                "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
                "verified": row.verified,
            }
            for row in rows
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _list_cell(value: object) -> tuple[str, ...]:
    if value is None or _text(value) == "":
        return ()
    if isinstance(value, (list, tuple)):
        return _unique(_text(item) for item in value if _text(item))
    raw = _text(value)
    if raw.startswith("["):
        decoded = json.loads(raw)
        if not isinstance(decoded, list):
            raise ValueError("list cell JSON must be an array")
        return _unique(_text(item) for item in decoded if _text(item))
    separator = ";" if ";" in raw else "\n"
    return _unique(part.strip() for part in raw.split(separator) if part.strip())


def _required_bool(value: object, field: str) -> bool:
    parsed = _optional_bool(value, field)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def _optional_bool(value: object, field: str) -> bool | None:
    if value is None or _text(value) == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = _text(value).lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"{field} must be true or false")


def _optional_datetime(value: object) -> datetime | None:
    if value is None or _text(value) == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
