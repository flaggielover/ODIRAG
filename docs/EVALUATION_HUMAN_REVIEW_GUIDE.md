# Phase J Human Evaluation Review Guide

Status: `HUMAN_REVIEW_INFRASTRUCTURE = PASS-LOCAL`
Evaluation status remains `HUMAN_EVALUATION = BLOCKED-HUMAN` until every row is reviewed.

## Review the workbook

1. Open `data/evaluation/eval_human_review.xlsx` in Excel.
2. Use the filters to review one category or refusal case at a time.
3. Read the question, expected answer, real evidence excerpt, document title, source URL,
   document ID, and chunk ID before choosing a verdict.
4. Select one value in `human_verdict`:
   - `PASS`: the question, expected answer, refusal decision, and evidence links are correct.
   - `FIX`: enter a complete `human_corrected_answer`; optionally correct
     `human_corrected_should_refuse` and add real chunk IDs in
     `human_additional_chunk_ids`.
   - `REJECT`: the candidate must not enter the verified evaluation set.
5. Add useful reasoning in `human_notes`. `reviewed_at` may be an ISO-8601 timestamp; if it
   is blank, the importer records the explicit apply time for reviewed rows.
6. Save the workbook without renaming or removing columns.

Do not mark a row `PASS` only because the wording sounds plausible. Every positive answer must
be supported by the listed real document and chunk. A refusal case may legitimately have no
expected evidence IDs.

## Validate without writing

The importer is dry-run by default:

```powershell
python scripts/import_human_evaluation_review.py
```

The output includes exactly these counters:

- `TOTAL`
- `REVIEWED`
- `UNREVIEWED`
- `PASS`
- `FIX`
- `REJECT`
- `VERIFIED`
- `TRACEABILITY_ERRORS`

Expected status before all 100 rows are reviewed: `PARTIAL_HUMAN_REVIEW`. Dry-run never writes
to PostgreSQL and never creates `phase_j_human_verified.json`.

## Apply explicit decisions

After the dry-run reports `TRACEABILITY_ERRORS=0`, apply the decisions explicitly:

```powershell
python scripts/import_human_evaluation_review.py --apply
```

Only `PASS` and a valid `FIX` with a non-empty corrected answer are stored with
`verified=true`. `REJECT` and unreviewed rows remain `verified=false`. The importer creates
`data/evaluation/phase_j_human_verified.json` only when `UNREVIEWED=0`; it never reports
`HUMAN_REVIEW_COMPLETE` for a partial workbook.

If a traceability error is reported, correct the workbook rather than bypassing validation.
Common errors include an unknown document ID, unknown chunk ID, source URL mismatch, a chunk
that belongs to a different document, a duplicate row ID, or an invalid verdict.
