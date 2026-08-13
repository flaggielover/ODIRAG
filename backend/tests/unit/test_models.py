from sqlalchemy import UniqueConstraint

import app.models  # noqa: F401
from app.database.base import Base

EXPECTED_TABLES = {
    "users",
    "sources",
    "source_candidate_columns",
    "source_candidates",
    "source_discovery_events",
    "source_discovery_runs",
    "source_columns",
    "crawl_tasks",
    "crawl_task_failures",
    "coze_invocations",
    "documents",
    "document_metadata_corrections",
    "document_versions",
    "attachments",
    "document_reviews",
    "structured_knowledge",
    "chunks",
    "prompt_versions",
    "retrieval_configs",
    "evaluation_questions",
    "evaluation_runs",
    "experiments",
    "query_traces",
    "alerts",
    "user_feedback",
    "data_lineage",
}


def test_all_core_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_document_business_identifiers_are_unique() -> None:
    document = Base.metadata.tables["documents"]
    chunk = Base.metadata.tables["chunks"]
    trace = Base.metadata.tables["query_traces"]

    assert document.c.document_id.unique is True
    assert chunk.c.chunk_id.unique is True
    assert trace.c.trace_id.unique is True
    assert trace.c.evidence_decision_json.nullable is False
    assert trace.c.rerank_metadata_json.nullable is False


def test_document_version_has_composite_unique_constraint() -> None:
    table = Base.metadata.tables["document_versions"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("document_id", "version") in unique_columns


def test_lineage_foreign_keys_cover_the_pipeline() -> None:
    lineage = Base.metadata.tables["data_lineage"]
    target_tables = {foreign_key.column.table.name for foreign_key in lineage.foreign_keys}
    assert {
        "sources",
        "crawl_tasks",
        "documents",
        "document_versions",
        "attachments",
        "chunks",
        "evaluation_runs",
    }.issubset(target_tables)
