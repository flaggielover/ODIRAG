# Evidence Sufficiency and Citation Safety Design

## Context

The existing live RAG path correctly refuses when retrieval returns zero hits, but a non-empty
retrieval result can still be unrelated to the question. Grounding currently treats any shared
Chinese bigram as coverage and prepares citations for every otherwise eligible hit. This allowed
an unrelated live question to reach the Direct LLM and return citations even though the generated
answer admitted that the evidence did not answer the question.

The verified crawl, review, chunking, embedding, Qdrant, hybrid retrieval, Direct LLM, and source
trust paths remain unchanged. This phase adds a fail-closed policy layer between retrieval/rerank
and grounding.

## Decision

Add an independent deterministic `EvidenceSufficiencyGate` with this result contract:

```json
{
  "sufficient": true,
  "confidence": 0.91,
  "reason": "evidence_covers_all_query_aspects",
  "supported_chunk_ids": ["chunk-id"],
  "unsupported_aspects": []
}
```

The gate extracts substantive query aspects, ignores generic question language, requires entity
and relation coverage, and enforces exact constraints for years, dates, percentages, and other
explicit numeric values. A multi-part question is sufficient only when every substantive aspect
is covered by one or more hits. A date/list/quantity question additionally requires corresponding
answer-shaped evidence.

Only `supported_chunk_ids` continue to grounding and the Direct LLM. An insufficient result is a
local refusal: the Direct LLM is not called and citations are empty. A model-generated citation
must still be a member of the supported set and map to the stored retrieval hit. Existing official
source, conflict, freshness, URL, strict Pydantic, and refusal rules remain in force.

## Auditability

Each query trace stores the full sufficiency decision in a dedicated JSON column. The chat response
and trace API expose the same decision. Operational metrics count sufficient and insufficient
decisions, grounding failures, citation-bearing answers, and refused answers that incorrectly
retained citations. Evaluation reports retain refusal accuracy and citation precision/recall while
adding answer-grounding and unsupported-answer rates.

## Configuration

The gate is enabled by default and fail-closed. Configuration only controls documented bounded
thresholds; production validation prevents disabling the gate outside development/test. No secret
or provider call is involved.

## Verification

Unit and integration coverage includes: unrelated questions, same-topic but unanswered questions,
partial multi-part support, same-name/different-entity questions, time-range mismatch, exact
numeric/date/list evidence, sufficient single-document evidence, and sufficient multi-chunk
evidence. The pre-existing 5/5 official live question must remain answerable, while the live
Mars/dinosaur regression must refuse before the Direct LLM and return zero citations.
