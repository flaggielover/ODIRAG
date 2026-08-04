# Experiments

The experiment framework compares isolated retrieval variants against the same verified dataset.
Each variant gets independent chunking, embedding, BM25/vector indexes, retrieval parameters,
filters, reranking, score threshold, and prompt version. Results link back to persisted evaluation
runs and expose metric deltas, regression flags, failed cases, and a conclusion.

## Configuration

Experiment YAML uses `schema_version: 1` and defines a name, type, dataset, output directory,
trusted runner, regression tolerance, lower-is-better metrics, and baseline/candidate parameters.
The committed example is `data/experiments/chunk_600_vs_800.yaml`.

```bash
backend/.venv/Scripts/python.exe scripts/run_experiment.py \
  --config data/experiments/chunk_600_vs_800.yaml
```

On POSIX systems, use the corresponding Python executable path. The runner import path is trusted
configuration and must not be accepted from untrusted users.

## Outputs

The experiment service writes `experiment.json`, `report.md`, and `chart_data.json` atomically.
The API also persists baseline and candidate evaluation runs so traces and lineage remain
inspectable. A regression is determined from configured tolerances and metric direction, not from
a hard-coded statement.

## Verified Example

The committed `chunk_600_vs_800` workflow ran successfully on 2026-08-03. It reported no
regression: answer-point coverage, document/chunk hit rates, MRR, nDCG@10, Recall@1/5/10,
citation completeness, refusal accuracy, cost, and scoped hallucination rate were unchanged;
candidate P95 latency changed from 1 ms to 0 ms in the deterministic run. These tiny latency values
reflect local fixture execution and are not production performance claims.

## Adding an Experiment

1. Add or select a verified dataset.
2. Change one controlled set of parameters per experiment.
3. Record provider, prompt, embedding, and rerank versions.
4. Run the baseline and candidate through the same evaluation path.
5. Inspect failed questions, traces, citations, and lineage before accepting the conclusion.
6. Commit configuration and curated fixtures; keep generated run artifacts out of Git unless they
   are deliberately selected as release evidence.

