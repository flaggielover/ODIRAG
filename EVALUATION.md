# Evaluation

ODIRAG evaluates the same retrieval, routing, grounding, citation, and refusal code used by the
chat API. Evaluation questions are persisted and must be verified before a run. Metrics are never
filled from constants: `EvaluationApplicationService` invokes `ChatService`, stores traces, records
lineage, and writes atomic artifacts.

## Dataset Contract

Each question includes a stable ID, text, expected query type, expected document/chunk IDs,
expected answer points, metadata filters, refusal expectation, difficulty, category, creator, and
verification flag. The committed deterministic benchmark is
`data/evaluation/demo_benchmark.yaml`. Actionable negative feedback can be converted into a new
verified question through the feedback API.

## Metrics

- Retrieval: document/chunk hit rate, Recall@1/5/10, MRR, and nDCG@10.
- Answer quality: expected answer-point coverage.
- Citations: accuracy and completeness against expected/stored identities.
- Safety: refusal accuracy and citation-quote-scoped hallucination rate.
- Operations: P50/P95 latency, average tokens, and average cost.

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

## Verified Local Demo Result

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

This is a one-question engineering smoke, not a production-quality benchmark. The larger fixed
benchmark and experiment reports remain necessary after changes to prompts, chunking, embedding,
retrieval, reranking, routing, grounding, or refusal behavior.

## Regression Discipline

Treat metric thresholds as release gates only when the dataset size and environment justify them.
Inspect failed cases and traces before accepting a delta. Never compare runs that silently changed
the dataset, provider version, prompt version, or filter behavior.

