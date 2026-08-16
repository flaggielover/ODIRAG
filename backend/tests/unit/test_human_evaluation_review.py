from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.evaluation.human_review import (
    REVIEW_STATUS_COMPLETE,
    REVIEW_STATUS_PARTIAL,
    WORKBOOK_COLUMNS,
    TraceabilityIndex,
    _evaluation_question,
    execute_human_review,
    parse_review_rows,
    validate_review_rows,
)


def _record(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "q-1",
        "category": "fact",
        "difficulty": "easy",
        "question": "What is supported?",
        "expected_answer": "Supported answer",
        "expected_document_ids": '["doc-1"]',
        "expected_source_urls": '["https://official.example/doc-1"]',
        "expected_chunk_ids": '["chunk-1"]',
        "evidence_excerpt": "Real persisted evidence.",
        "source_title": "Official Example",
        "document_title": "Document One",
        "region": "Sichuan",
        "temporal_constraint": "2026-01-01",
        "should_refuse": False,
        "human_verdict": "",
        "human_corrected_answer": "",
        "human_corrected_should_refuse": "",
        "human_additional_chunk_ids": "",
        "human_notes": "",
        "reviewed_at": "",
    }
    record.update(changes)
    assert set(record) == set(WORKBOOK_COLUMNS)
    return record


def _traceability() -> TraceabilityIndex:
    return TraceabilityIndex(
        document_urls={"doc-1": "https://official.example/doc-1"},
        chunk_documents={"chunk-1": "doc-1", "chunk-2": "doc-1"},
        chunk_contents={
            "chunk-1": "Real persisted evidence.",
            "chunk-2": "Additional persisted evidence.",
        },
        document_titles={"doc-1": "Document One"},
        source_titles={"doc-1": "Official Example"},
    )


def _output_path() -> Path:
    output = Path(".test-data") / "human-review" / f"{uuid.uuid4()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


@pytest.mark.parametrize(
    ("verdict", "corrected_answer", "verified"),
    [("PASS", "", True), ("FIX", "Corrected answer", True), ("REJECT", "", False)],
)
def test_pass_fix_and_reject_verification_rules(
    verdict: str, corrected_answer: str, verified: bool
) -> None:
    row = parse_review_rows(
        [_record(human_verdict=verdict, human_corrected_answer=corrected_answer)]
    )[0]
    assert row.verified is verified
    if verdict == "FIX":
        assert row.effective_answer == "Corrected answer"


def test_fix_can_correct_refusal_and_add_traceable_chunks() -> None:
    row = parse_review_rows(
        [
            _record(
                human_verdict="FIX",
                human_corrected_answer="Insufficient evidence.",
                human_corrected_should_refuse=True,
                human_additional_chunk_ids='["chunk-2"]',
            )
        ]
    )[0]
    validation = validate_review_rows((row,), _traceability())
    assert validation.errors == ()
    assert row.effective_should_refuse is True
    assert row.effective_chunk_ids == ("chunk-1", "chunk-2")


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"human_verdict": "MAYBE"}, "INVALID_VERDICT:q-1"),
        ({"human_verdict": "FIX"}, "FIX_REQUIRES_CORRECTED_ANSWER:q-1"),
        ({"expected_document_ids": '["missing"]'}, "UNKNOWN_DOCUMENT:q-1:missing"),
        ({"expected_chunk_ids": '["missing"]'}, "UNKNOWN_CHUNK:q-1:missing"),
    ],
)
def test_invalid_review_and_traceability_are_reported(
    changes: dict[str, object], error: str
) -> None:
    validation = validate_review_rows(parse_review_rows([_record(**changes)]), _traceability())
    assert error in validation.errors


def test_evidence_excerpt_and_titles_must_match_persisted_records() -> None:
    validation = validate_review_rows(
        parse_review_rows(
            [
                _record(
                    evidence_excerpt="Generated replacement",
                    document_title="Wrong document",
                    source_title="Wrong source",
                )
            ]
        ),
        _traceability(),
    )
    assert "EVIDENCE_EXCERPT_MISMATCH:q-1" in validation.errors
    assert "DOCUMENT_TITLE_MISMATCH:q-1" in validation.errors
    assert "SOURCE_TITLE_MISMATCH:q-1" in validation.errors


def test_refusal_evidence_and_titles_must_match_persisted_records() -> None:
    validation = validate_review_rows(
        parse_review_rows(
            [
                _record(
                    should_refuse=True,
                    evidence_excerpt="Generated replacement",
                    document_title="Wrong document",
                    source_title="Wrong source",
                )
            ]
        ),
        _traceability(),
    )
    assert "EVIDENCE_EXCERPT_MISMATCH:q-1" in validation.errors
    assert "DOCUMENT_TITLE_MISMATCH:q-1" in validation.errors
    assert "SOURCE_TITLE_MISMATCH:q-1" in validation.errors


def test_duplicate_id_is_reported() -> None:
    rows = parse_review_rows([_record(), _record()])
    validation = validate_review_rows(rows, _traceability())
    assert "DUPLICATE_ID:q-1" in validation.errors


def test_partial_and_complete_statuses() -> None:
    partial = validate_review_rows(parse_review_rows([_record()]), _traceability())
    complete = validate_review_rows(
        parse_review_rows([_record(human_verdict="PASS")]), _traceability()
    )
    assert partial.status == REVIEW_STATUS_PARTIAL
    assert partial.counts["UNREVIEWED"] == 1
    assert complete.status == REVIEW_STATUS_COMPLETE
    assert complete.counts["VERIFIED"] == 1


def test_evaluation_question_uses_only_supported_non_leaking_filters() -> None:
    row = parse_review_rows([_record(human_verdict="PASS")])[0]
    question = _evaluation_question(row)
    assert question.expected_filters == {"region": "Sichuan"}


@pytest.mark.asyncio
async def test_dry_run_never_persists_or_writes_output() -> None:
    validation = validate_review_rows(
        parse_review_rows([_record(human_verdict="PASS")]), _traceability()
    )
    persisted: list[object] = []

    async def persist(questions: tuple[object, ...]) -> None:
        persisted.extend(questions)

    output = _output_path()
    result = await execute_human_review(
        validation, apply=False, output_path=output, persist=persist
    )
    assert result.applied is False
    assert persisted == []
    assert not output.exists()


@pytest.mark.asyncio
async def test_apply_persists_and_writes_only_complete_output() -> None:
    validation = validate_review_rows(
        parse_review_rows([_record(human_verdict="PASS")]), _traceability()
    )
    persisted: list[object] = []

    async def persist(questions: tuple[object, ...]) -> None:
        persisted.extend(questions)

    output = _output_path()
    try:
        result = await execute_human_review(
            validation,
            apply=True,
            output_path=output,
            persist=persist,
            reviewed_at=datetime(2026, 8, 14, tzinfo=UTC),
        )
        assert result.applied is True
        assert result.final_output_written is True
        assert len(persisted) == 1
        assert persisted[0].verified is True
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["status"] == REVIEW_STATUS_COMPLETE
        assert payload["questions"][0]["reviewed_at"] == "2026-08-14T00:00:00+00:00"
    finally:
        output.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_partial_apply_persists_but_does_not_claim_complete() -> None:
    validation = validate_review_rows(parse_review_rows([_record()]), _traceability())
    persisted: list[object] = []

    async def persist(questions: tuple[object, ...]) -> None:
        persisted.extend(questions)

    output = _output_path()
    try:
        result = await execute_human_review(
            validation, apply=True, output_path=output, persist=persist
        )
        assert result.status == REVIEW_STATUS_PARTIAL
        assert len(persisted) == 1
        assert persisted[0].verified is False
        assert not output.exists()
    finally:
        output.unlink(missing_ok=True)
