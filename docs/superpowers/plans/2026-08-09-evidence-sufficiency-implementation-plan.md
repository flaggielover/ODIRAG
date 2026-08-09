# Evidence Sufficiency Implementation Plan

1. Add the deterministic sufficiency decision and gate under `app.rag`.
2. Insert the gate after hybrid/rerank retrieval and before grounding; filter all downstream
   context and citations to supported chunks.
3. Persist the decision in `query_traces` through an Alembic migration and expose it in chat/trace
   schemas.
4. Extend operational and evaluation metrics for sufficiency, citation safety, answer grounding,
   and unsupported answers.
5. Add A-H unit cases, chat integration coverage, migration/config/API tests, and the strict Direct
   LLM refusal-contract regression.
6. Run focused and full quality gates, upgrade/check the real PostgreSQL schema, then repeat the
   existing 5/5 live answer and no-evidence acceptance checks.
7. Update implementation, production-readiness, acceptance, and learning documentation and create
   a local Git checkpoint without pushing.
