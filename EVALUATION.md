# Evaluation

ODIRAG evaluates the same retrieval, routing, grounding, citation, and refusal code used by the
chat API. Evaluation questions are persisted and must be verified before a run. Metrics are never
filled from constants: `EvaluationApplicationService` invokes `ChatService`, stores traces, records
lineage, and writes atomic artifacts.

## Dataset Contract

Each question includes a stable ID, text, expected query type, expected document/chunk IDs,
expected answer points, metadata filters, refusal expectation, difficulty, category, creator, and
verification flag. The repository contains both the small deterministic benchmark at
`data/evaluation/demo_benchmark.yaml` and the final 100-question human-verified Gold dataset at
`data/evaluation/phase_j_human_verified.json`. Actionable negative feedback can be converted into
a new verified question through the feedback API.

## Metrics

- Retrieval: document/chunk hit rate, Recall@1/5/10, MRR, and nDCG@5/10.
- Answer quality: expected answer-point coverage, grounded-answer rate, evidence-sufficiency
  accuracy, and Supported Answer Recall.
- Citations: exact chunk precision/recall, emitted-answer-only precision/recall, and diagnostic
  document-level precision/recall. Document-level metrics do not replace the exact chunk contract.
- Safety: refusal accuracy/precision/recall, unsupported-answer rate, and
  citation-quote-scoped hallucination rate.
- Operations: P50/P95 latency, average tokens, average cost, provider application coverage, and
  execution-error count.

Hallucination measurement is deliberately scoped. Only claims explicitly checked against stored
citation quotes contribute to its denominator; questions with no assessed claims are excluded.
This is not a general semantic truthfulness score.

## Running Evaluations

Use `POST /api/evaluations/run` with verified question IDs, or run the demo seed pipeline against a
configured environment:

```bash
python scripts/seed_demo.py --index --evaluate
```

The latter uses the configured embedding, cache, vector, and rerank providers. Provider failures
remain visible; the script does not replace them with fake responses. In Compose, the startup flow
seeds records and reindexes through the live API so the running process refreshes its BM25 state.

Each completed run writes:

- `evaluation.json` with aggregate and per-question evidence;
- `questions.csv` for tabular analysis;
- `report.md` for review;
- `chart_data.json` for visualization.

## Latest Human-Verified Gold Evaluation

The latest authoritative result is run 16, `phase-j-final-gold-100-20260815`, executed on
2026-08-15 through the real application evaluation path. It completed all 100 human-verified
questions with zero execution errors; no offline replay was substituted for the run. The recorded
configuration used `hybrid_rerank`, embedding model `text-embedding-3-small`, and remote rerank
model `rerank-v3.5` against the 182-document/821-chunk corpus. This run predates the later accepted
Bailian `text-embedding-v4` production migration, so it is the current Gold quality baseline, not
a post-migration 100-question benchmark of the present provider chain.

| Metric | Run 16 value |
| --- | ---: |
| Questions / execution errors | 100 / 0 |
| Recall@5 / Recall@10 | 0.885000 / 0.885000 |
| MRR | 0.840667 |
| nDCG@5 / nDCG@10 | 0.806227 / 0.806227 |
| Exact Citation Precision / Recall | 0.288069 / 0.433333 |
| Emitted Exact Citation Precision / Recall | 0.447003 / 0.672414 |
| Emitted Document Citation Precision / Recall | 0.913793 / 0.905172 |
| Grounded Answer Rate | 0.948276 (55/58) |
| Refusal Accuracy / Precision / Recall | 0.680000 / 0.238095 / 1.000000 |
| Unsupported Answer Rate | 0.000000 |
| Evidence Sufficiency Accuracy | 0.960000 |
| Supported Answer Recall | 0.644444 (58/90) |

The correct status is `GOLD_EVALUATION_QUALITY=PARTIAL` and
`QUALITY_GUARD=FAIL-LIVE-QUALITY`. All 10 Gold refusal questions were safely refused without
citations or unsupported answers, but 32/90 supported questions were refused. Exact citation
precision/recall also remains weak; the failure analysis separates false refusals, incomplete
multi-chunk citations, and Gold seed mismatches that still hit a valid supporting document.

Remote rerank provider acceptance is `PASS-LIVE`, but run-wide application coverage was only
`PARTIAL-LIVE`: 67/100 traces applied remote reranking and 33/100 failed open on HTTP 429. Evidence
retention did not fall from Top 10 to rerank, so those 429 responses are a capacity/reliability
limit rather than the primary explanation for the supported false refusals.

Authoritative artifacts:

- `data/evaluation/gold_metrics.json`
- `data/evaluation/gold_summary.md`
- `data/evaluation/gold_run_16/`
- `GOLD_EVALUATION_FAILURE_ANALYSIS.md`

## Historical Deterministic Engineering Smoke

On 2026-08-04, the Phase 15 deterministic smoke indexed two approved documents into six chunks and
ran the verified question `软件企业研发投入支持措施` through the real router, hybrid retrieval,
grounding, citation, trace, and report pipeline. The measured result was:

| Metric | Actual value |
| --- | ---: |
| Questions | 1 |
| Recall@1 / @5 / @10 | 1.0 / 1.0 / 1.0 |
| MRR / nDCG@10 | 1.0 / 1.0 |
| Answer-point coverage | 1.0 |
| Citation accuracy / completeness | 1.0 / 1.0 |
| Refusal accuracy | 1.0 |
| Scoped hallucination rate | 0.0 over 3 assessed claims |
| P50 / P95 latency | 4 ms / 4 ms |
| Average tokens / cost | 0 / 0.0 (extractive deterministic mode) |

This is a one-question engineering smoke, not a production-quality benchmark and not the current
Gold result. It remains useful for deterministic pipeline regression only.

## Regression Discipline

Treat metric thresholds as release gates only when the dataset size and environment justify them.
Inspect failed cases and traces before accepting a delta. Never compare runs that silently changed
the dataset, provider version, prompt version, or filter behavior. Changes that can affect answer
quality should run focused deterministic checks and, when the required live environment is
available, the 100-question Gold evaluation and quality guard. Any skipped live rerun remains
`UNVERIFIED`; production health or provider smoke tests do not substitute for Gold quality evidence.
