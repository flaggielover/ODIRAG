# Phase N-O-P Local Closure Design

## Scope

This design implements the already approved Phase N, O, and P requirements without
changing the grounded RAG, Embedding, Qdrant, Direct LLM, Remote Rerank, or Brave
provider contracts. It does not create crawl tasks or expand the corpus.

## Phase N: attachments

Attachment processing remains a separate, auditable pipeline. A detector combines
response MIME type, Content-Disposition filename, byte signatures, the original
attachment name, and the URL path. The existing SSRF-safe `HttpFetcher` performs all
network reads and revalidates every redirect. Successful bytes are stored under the
existing bounded attachment storage root. Download audit fields and parsing outcome
fields remain distinct so a parser failure cannot erase the network evidence.

Reliable local parsers remain PDF text, DOCX, XLSX, TXT, and HTML. DOC/XLS are terminal
`unsupported_legacy_format` unless a reliable runtime parser is present. Images and
low-text PDFs use an injectable OCR contract; without a configured real provider they
terminate honestly as `OCR_UNAVAILABLE`. Parsed file hashes make repeated processing a
cache hit. Existing attachment-aware chunk provenance remains the integration path;
Phase N does not invoke paid Embeddings or reindex the live corpus.

## Phase O: performance

Performance analysis uses persisted PostgreSQL `QueryTrace.stage_timings_json` and a
fixed, versioned benchmark. Warm-up samples are excluded. The benchmark reports three
formal runs and percentile statistics per stage. Only a trace-proven local bottleneck
may be changed. Quality checks retain Evidence Sufficiency, official grounding,
citation validation, refusal handling, and Hybrid Retrieval. If the external Direct
LLM remains the dominant floor or P95 stays above five seconds, the result is PARTIAL.

## Phase P: human evaluation

The review workbook contains the 100 draft questions plus evidence copied from real
PostgreSQL documents/chunks. Human verdict cells start blank and accept only PASS, FIX,
or REJECT. The importer defaults to dry-run, validates identifiers and traceability,
and writes only with explicit `--apply`. It never marks an unreviewed or rejected row
verified and only creates the final verified dataset after all rows are reviewed.

## Verification and rollback

Each phase has focused tests, followed by full backend checks. Phase Q verifies the
eight-service runtime, database counts, Redis, Qdrant, HTTP health, and the existing
5/5 live closed loop. Migrations are additive and downgradeable. No destructive volume,
database, or corpus operation is part of this design.
