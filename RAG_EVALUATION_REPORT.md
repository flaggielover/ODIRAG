# RAG Evaluation Report

Last updated: 2026-08-13

## Verdict

Phase J produced a 100-case **DRAFT_EVAL_SET** from the real PostgreSQL corpus. It is not human-verified and has not been used to claim release-quality metrics.

Status: **BLOCKED-HUMAN-EVAL-REVIEW**. Remote `hybrid_rerank` is additionally **BLOCKED-EXTERNAL-RERANK-KEY**.

## Dataset evidence

| Property | Actual |
| --- | ---: |
| Candidate cases | 100 |
| Human verified | 0 |
| Human review required | 100 |
| Distinct real document IDs referenced | 93 |
| Distinct real chunk IDs referenced | 93 |
| Distinct official source domains referenced | 11 |
| Refusal/safety candidates | 10 |
| Required categories represented | 18 / 18 |

The generator reads only approved, indexed documents from sources whose persisted `official_status` is `official`; it joins each document to an indexed chunk. Each positive candidate contains the real document ID, source URL, chunk ID, region, publication constraint, and an evidence excerpt. It excludes association sources from positive official-evidence candidates.

The 18 represented categories are explicit fact, date, number, list, policy condition, implementation scope, multi-document, attachment question, OCR document, same-topic misdirection, temporal mismatch, regional mismatch, association-vs-official, no evidence, adversarial, partial evidence, requires refusal, and multi-hop.

Artifacts:

- `data/evaluation/phase_j_draft.json`: reviewable candidate set.
- `data/evaluation/evaluation_results.json`: machine-readable `NOT_RUN` result with null metrics.

## Why metrics are not published

An AI-generated expected answer is only a candidate. A human must validate the question wording, expected answer, evidence completeness, additional relevant chunks, refusal expectation, region, and temporal constraint. Until then, reporting Recall, MRR, nDCG, citation quality, grounded-answer rate, refusal accuracy, or unsupported-answer rate would create false precision.

Accordingly, all formal metrics are `null`, not zero and not one:

- Recall@5 / Recall@10
- MRR
- nDCG@5 / nDCG@10
- Citation accuracy / precision / recall
- Grounded answer rate
- Refusal accuracy
- Unsupported answer rate

Existing one-question and two-question live checks remain plumbing evidence only; they are not substituted for this representative evaluation.

## Verification

- Phase J dataset/evaluation targeted regression: 11 passed.
- Dataset contract enforces `DRAFT_EVAL_SET`, `human_verified_count=0`, traceability for positive cases, unique IDs, and all required categories.
- Ruff: PASS.
- mypy: PASS across 158 source files.
- Real generation: 100 cases from real PostgreSQL approved/indexed official records; no CrawlTask and no external provider call were created.

## Minimum human action

Review the fields `question`, `expected_answer`, `expected_documents`, `expected_sources`, `expected_chunk_ids`, `should_refuse`, `region`, and `temporal_constraint`. Only reviewed cases may be persisted with `verified=true` and used for the four-mode evaluation matrix.
