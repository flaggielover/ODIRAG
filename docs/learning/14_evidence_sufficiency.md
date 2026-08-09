# Evidence Sufficiency and Citation Safety

## Why this layer exists

Retrieval always returns the nearest available chunks. A non-empty top-k result therefore proves
ranking behavior, not that the corpus can answer the question. ODIRAG keeps retrieval reusable for
search/debugging and adds a fail-closed answer policy after Hybrid/Rerank:

```text
query -> Hybrid/Rerank -> Evidence Sufficiency -> Grounding -> Direct LLM -> citation validation
```

`backend/app/rag/evidence.py` evaluates every substantive question aspect, exact year/date/number
constraints, and typed answer-shape requirements such as dates, percentages, money, lists, or
contact details. High-risk relations such as cancellation and penalties must be bound to the
requested entity inside the same chunk and a short proximity window. Scope questions additionally
require the requested target and an applicability verb in the same chunk. This prevents an
unrelated phrase elsewhere in the same document from satisfying the gate. Raw retrieval scores are
not compared because BM25, vector, RRF, and rerank scores use different scales.

## Runtime contract

The decision contains `sufficient`, `confidence`, `reason`, `supported_chunk_ids`, and
`unsupported_aspects`. Only supported IDs reach Grounding and the answer provider. When evidence is
insufficient, `/api/chat` returns a normal safe refusal, never calls the answer LLM, and always
returns an empty citation list.

After generation, cited chunks are checked again against the complete question and every answer
sentence is checked independently, so one supported sentence cannot hide a later unsupported
claim. Exact values, relations, scope targets, polarity, and the requested answer shape must occur
in the question or cited evidence. A failed post-check becomes `answer_not_supported_by_citations`,
`answer_contains_unsupported_claim`,
`answer_contains_unsupported_relation`, `answer_contains_unsupported_scope_target`,
`answer_contains_unsupported_scope_polarity`, `answer_missing_required_shape`, or
`answer_contains_unsupported_exact_values`, with citations removed. Existing official-source,
conflict, freshness, strict Pydantic, citation-ID, and URL rules still apply. When official-only is
enabled, non-official hits are removed before Grounding creates LLM context or citations. Numeric
facts such as penalty amounts remain RAG questions; only explicit corpus-count language is routed
to the structured document count path.

## Audit and metrics

Migration `0007_evidence_sufficiency` adds `query_traces.evidence_decision_json`. It stores only the
decision, counts, latency, provider/model identifiers, refusal reasons, and post-check status. It
does not duplicate chunk bodies or credentials. `/api/chat`, trace APIs, the query inspector, and
monitoring expose the same result.

Operational metrics include gate assessed/sufficient/insufficient counts, pass rate, average gate
latency, grounding failures, citation rate, and the invariant violation count for citations on a
refusal. Evaluation citation precision/recall exclude only correctly refused cases, so empty refusal
citations cannot inflate the score while an unsupported answer still enters the denominator. The
normal evaluation adapter independently compares answer claims and exact values with cited chunk
content; an external evaluator may additionally supply `grounding_validated`. ChatService's own
`answer_support_validated` result is not fed back as evaluation ground truth; that runtime field
remains audit data.

## Verification

Run the deterministic A-H regression and full backend suite:

```powershell
cd D:\RAG\backend
.\.venv\Scripts\python.exe -m pytest tests/unit/test_evidence_sufficiency.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Run the live acceptance without printing local credentials:

```powershell
cd D:\RAG
docker compose run --rm --no-deps -e ODIRAG_RUN_MIGRATIONS=false -v D:\RAG\scripts:/app/scripts backend python /app/scripts/live_accept_evidence_sufficiency.py --base-url http://backend:8000/api
powershell -NoProfile -ExecutionPolicy Bypass -File D:\RAG\scripts\run_live_playwright.ps1
```

The live script requires one supported Direct LLM call, then proves that the non-empty Mars/dinosaur
retrieval and three adversarial APP-filing questions are refused with zero citations, zero answer
tokens, and zero cost. The adversarial set covers an unrelated cancellation phrase in the same
official document, a missing penalty amount, and a missing WeChat mini-program applicability fact.
Fixture success must not be reported as PASS-LIVE.

## Troubleshooting

- `evidence_constraint_mismatch`: an exact query year/date/number is absent from retrieved evidence.
- `evidence_missing_required_answer_shape`: content is topically related but lacks the requested
  date, amount, list, or contact detail.
- `evidence_missing_required_relation`: a relation word exists only outside the requested entity
  context, or no chunk directly supports the relation.
- `evidence_missing_required_scope_target`: a scope target is absent or not bound to an
  applicability statement in one chunk.
- `insufficient_evidence_relevance`: core entity/relation coverage is below the fixed safe floor.
- `citations_do_not_cover_query`: the model cited only a subset that cannot support every aspect.
- A refusal with citations is a contract violation; check `refusal_citation_violation_count` and do
  not mask it in evaluation code.
