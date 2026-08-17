# Phase K Performance Report

> Historical latency and capacity evidence: later Gold run 16 supersedes the Gold quality metrics
> cited in this report, while the fixed 60-sample performance matrix remains a separate historical
> measurement. Current quality status is in `EVALUATION.md`; current production acceptance is in
> `PRODUCTION_READINESS_REPORT.md`. Neither this report nor bounded Phase 5 smoke evidence is a
> long-term production SLA.

## Phase AD human-gold performance checkpoint (2026-08-14, authoritative)

The formal human-verified Gold run `6` executed 100 real evaluation questions through
the live evaluation API. It recorded P50 latency `3896 ms` and P95 latency `8121 ms`.
This is a quality/evaluation workload, not a replacement for the fixed 20-question
performance matrix below; both independently miss the `<5000 ms` P95 target.

The Gold run persisted 100 remote-provider traces, 68 applied reranks, and 31
fail-open traces. Retrieval quality was Recall@5/10 `0.885`, MRR `0.809`, and
nDCG@5/10 `0.789022`; answer quality did not pass the independent guard because
both intended-supported guard cases refused. No latency, evidence, citation,
refusal, or provider threshold was relaxed.

Authoritative artifacts:

- `data/evaluation/gold_run_6/gold_metrics.json`
- `data/evaluation/gold_run_6/gold_summary.md`
- `data/evaluation/gold_quality_run_7/`

Status: `GOLD_EVALUATION=COMPLETE-WITH-QUALITY-FAILURE`,
`RAG_PERFORMANCE_P95=PARTIAL`.

## Phase AA-AC performance closure (historical, superseded by Phase AD)

This section supersedes older performance snapshots below where they differ. The
fixed workload is `data/evaluation/phase_ab_benchmark.json`: 20 Phase-J draft
questions used only for performance, three total warm-up requests, and three
independent runs. The final report contains 60 valid samples. Six run-1 samples
were recovered from current-instrumentation traces after a transient provider
failure; 54 further successful requests and one bounded transient retry completed
the matrix. Brave was not called.

| Metric | Before optimization | After optimization | Change |
|---|---:|---:|---:|
| P50 | 2,582 ms | 1,638 ms | -36.6% |
| P95 | 8,763 ms | 6,774 ms | -22.7% |
| P99 | 10,082 ms | 9,129 ms | -9.5% |
| P95 target | `<5000 ms` | not met | `PARTIAL` |

The before artifact is
`data/performance/phase-ab-before-20260814T074402Z.json`; the authoritative after
artifact is `data/performance/phase-ab-after-20260814T084535Z.json`. Per-run after
results were:

| Run | P50 | P95 | P99 | Embedding P95 | Remote Rerank P95 | Direct LLM P95 |
|---|---:|---:|---:|---:|---:|---:|
| 1, partially warm | 2,885 ms | 7,443 ms | 9,129 ms | 2,846.955 ms | 1,580.243 ms | 6,737.128 ms |
| 2, warm | 1,297 ms | 6,143 ms | 6,774 ms | 2.667 ms | 1,776.537 ms | 5,252.173 ms |
| 3, warm | 1,304 ms | 6,056 ms | 7,395 ms | 2.850 ms | 1,484.596 ms | 6,215.473 ms |

The measured optimizations were deliberately limited to two semantics-neutral
boundaries:

- a fail-open, versioned Redis query-embedding cache keyed by provider, model,
  endpoint fingerprint, embedding version, and query digest, including concurrent
  same-query coalescing;
- shared HTTP connection pools for Remote Embedding and Direct LLM requests, with
  bounded shutdown cleanup.

Remote Rerank code, provider, top-k, evidence thresholds, Grounding, Answer
Validation, Citation, refusal rules, and final context content were not changed.
The warm embedding P95 fell below 3 ms, while local BM25/vector/fusion/evidence/
context/citation stages remained small. The remaining tail is external-provider
dominated: overall Direct LLM P95 was 6,737.128 ms and Remote Rerank P95 was
1,580.243 ms. The best complete-run P95 was 6,056 ms. Warm local controllable work
is approximately tens of milliseconds; the required provider calls set the
practical floor, so no defensible quality-preserving local change can claim
`P95 < 5000 ms` from this evidence.

The separate four-case live quality guard is
`data/performance/phase-ab-after-20260814T084733Z.json`. Remote Rerank applied in
4/4 cases and both unsupported cases safely refused with zero citations. Both
intended-supported, non-human-verified fixtures also refused: one at Evidence
Sufficiency and one after `answer_contains_unsupported_relation`. No unsafe answer
escaped, but the required supported-answer gate was 2/4 overall and therefore
`FAIL-LIVE-QUALITY-REGRESSION`; it was not retried into a pass and no safety rule
was relaxed.

Final status: `RAG_PERFORMANCE_P95=PARTIAL`. The provider/full-RAG acceptance from
the prior verified traces remains `REMOTE_RERANK_PROVIDER=PASS-LIVE` and
`REMOTE_RERANK_FULL_RAG=PASS-LIVE`; this benchmark does not replace that separate
acceptance gate.

## Historical Phase O measured closure (superseded, 2026-08-14)

The historical profile artifact was
`data/performance/phase-o-20260813T172006Z.json`. It used two fixed real-corpus
cases, one warm-up per case, three ordered runs, the real remote
Embedding/Qdrant/Hybrid Retrieval/Evidence Gate/Direct LLM path, and no Remote
Rerank or Brave calls. Six measured samples produced:

| Metric | Current result |
|---|---:|
| P50 | 734.236 ms |
| P75 | 3755.127 ms |
| P95 | 5121.708 ms |
| P99 | 5121.708 ms |
| Max | 5121.708 ms |
| P95 target `<5000 ms` | **not met** |

Stage P95 values: query embedding `1042.8 ms`, retrieval total `1076.773 ms`, and
Direct LLM `4012.936 ms`. The benchmark status is
`PASS-LIVE-INSTRUMENTATION`, not quality acceptance: the fixed set has zero human
verified cases and its quality guard is `BLOCKED-HUMAN-VERIFICATION`. No quality or
grounding behavior was relaxed to reduce latency. Historical Phase K results below
remain useful context but are not the current benchmark snapshot.

Date: 2026-08-13
Status: **PROFILED-LIVE / TARGET-NOT-MET**

This report separates historical production-like trace evidence from fixture or inferred results. No retrieval threshold, Grounding rule, Evidence Sufficiency rule, citation validation, or context selection behavior was weakened.

## Live trace baseline

The baseline uses all 69 persisted RAG `query_traces` available before Phase K instrumentation. One SQL-only trace is excluded.

| Cohort | Count | P50 | P95 | P99 / max | Result |
|---|---:|---:|---:|---:|---|
| All RAG | 69 | 1,556 ms | 7,184 ms | 8,041 / 8,041 ms | P50 goal passes; P95 goal fails |
| Answered | 17 | 5,873 ms | 7,424 ms | 7,424 / 7,424 ms | P50 and P95 goals fail |
| Refused | 52 | 1,465 ms | 5,099 ms | 8,041 / 8,041 ms | P50 passes; P95 narrowly fails |

Policy targets are `P50 < 3000 ms` and `P95 < 5000 ms`. Therefore:

`RAG_P95_LT_5000MS = FAIL-LIVE`

## Historical stage evidence

| Stage | Historical evidence | Status |
|---|---|---|
| Query analysis | Not persisted separately | UNOBSERVED-HISTORICAL |
| Embedding | Not persisted separately | UNOBSERVED-HISTORICAL |
| BM25 | Not persisted separately | UNOBSERVED-HISTORICAL |
| Vector | Not persisted separately | UNOBSERVED-HISTORICAL |
| Fusion | Not persisted separately | UNOBSERVED-HISTORICAL |
| Rerank | provider disabled; recorded average/P95 `0 ms` | NOT APPLICABLE TO REMOTE RERANK |
| Evidence Sufficiency | average `0.374 ms`; P95 `0.961 ms` over 69 RAG traces | MEASURED-LIVE |
| Grounding | Not persisted separately | UNOBSERVED-HISTORICAL |
| Direct LLM | Not persisted separately | UNOBSERVED-HISTORICAL |
| Citation validation | Not persisted separately | UNOBSERVED-HISTORICAL |

Answered requests have a substantially higher median than refused requests. This is evidence that the post-retrieval answer path, including the real Direct LLM call, is the dominant *candidate* bottleneck. It is not enough evidence to assign the entire delta to Direct LLM, because historical traces did not persist the complete stage split.

## Usage and cost evidence

- Token usage is available on 22/69 RAG traces: average `3,368.77` tokens/query.
- Answered token usage is available on 17/17 traces: average `3,371.12` tokens/query.
- Stored cost is numerically zero, but the provider records `cost_measurement=not_available`; zero must not be interpreted as a free request.
- A defensible cost/query value is therefore **UNAVAILABLE**, not `0`.

## Phase K instrumentation

Migration `0010_query_trace_stage_timings` adds non-null `query_traces.stage_timings_json`. New traces persist:

- `query_routing`
- `structured_query` when used
- `retrieval_analysis`
- `retrieval_embedding`
- `retrieval_bm25`
- `retrieval_vector`
- `retrieval_fusion`
- `retrieval_rerank` when invoked
- `retrieval_total`
- `evidence_gate`
- `grounding`
- `direct_llm`
- `citation_validation`
- `total`

The trace API exposes the stage map. The implementation changes only timing metadata and does not alter answer, retrieval, refusal, Grounding, or citation behavior.

Verification:

- Targeted chat/model/API regression: `12 passed`.
- Ruff: pass.
- mypy: pass, 158 source files.
- SQLite fresh migration, downgrade to `0009`, re-upgrade to `0010`, and `alembic check`: pass.
- Real PostgreSQL upgrade/current/check at `0010`: pass with no drift.
- Minimal backend-only rebuild: pass; all eight Compose services are healthy afterward.
- Black 25.12.0: `PASS-LOCAL` with an isolated workspace cache and explicit source scopes (`backend/app`, `backend/tests`, `backend/alembic`, plus the two changed scripts); caches and generated/data directories were excluded.

## Live instrumented samples

Two final acceptance rows were selected from the newly persisted traces. They are real HTTP/API executions against PostgreSQL, Redis, remote embedding, Qdrant and the configured answer path; they are not fixtures and are not used to claim a population latency SLA.

| Case | Retrieval | Evidence/answer outcome | Persisted stage keys | Total |
|---|---:|---|---|---:|
| Supported MIIT APP-filing question | 5 hits | sufficient; Direct LLM called; 2,907 tokens; one title/URL/chunk citation | routing, analysis, embedding, BM25, vector, fusion, retrieval total, evidence gate, grounding, Direct LLM, citation validation, total | 5,198 ms |
| Unsupported fictional question | 5 candidates | insufficient; refusal; zero citations; zero answer-LLM tokens | routing, analysis, embedding, BM25, vector, fusion, retrieval total, evidence gate, total | 1,355 ms |

Every stored value is numeric and non-negative. The refusal trace intentionally has no `grounding`, `direct_llm`, or `citation_validation` entry because those stages were not executed. Query trace count increased from 70 to 83 during repeated acceptance diagnostics; documents, approvals, chunks and Qdrant points did not change. These two samples confirm instrumentation correctness, not the `P95 < 5000 ms` performance target.

## Optimization decision

No candidate-pool reduction, top-k reduction, prompt truncation, cache policy change, timeout reduction, or safety bypass was applied. At this Phase K checkpoint, the 100-case evaluation set was still `DRAFT_EVAL_SET` with zero human-verified cases, so there was no trustworthy same-dataset quality guard for an optimization experiment. Later human review and Gold runs supersede that dataset-status statement; this paragraph records why no performance optimization was applied at the time.

At the Phase K checkpoint, remote rerank latency and cost were `BLOCKED-EXTERNAL-RERANK-KEY` and the provider was disabled. Later Cohere acceptance and Gold run 16 supersede provider availability, but do not retroactively create remote-rerank measurements for this earlier performance matrix.
