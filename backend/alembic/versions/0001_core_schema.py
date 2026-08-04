"""Create the ODIRAG core relational schema.

Revision ID: 0001_core_schema
Revises: None
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_core_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("token_version >= 0", name="ck_users_token_version_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_active_role", "users", ["is_active", "role"], unique=False)

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("organization_level", sa.String(length=64), nullable=True),
        sa.Column("organization_type", sa.String(length=64), nullable=True),
        sa.Column(
            "official_status", sa.String(length=32), nullable=False, server_default="official"
        ),
        sa.Column("homepage_url", sa.String(length=2048), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("crawl_frequency", sa.String(length=64), nullable=False, server_default="daily"),
        sa.Column("last_crawl_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("priority >= 0", name="ck_sources_priority_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("source_key", name="uq_sources_source_key"),
    )
    op.create_index("ix_sources_city", "sources", ["city"], unique=False)
    op.create_index("ix_sources_domain", "sources", ["domain"], unique=False)
    op.create_index("ix_sources_enabled_priority", "sources", ["enabled", "priority"], unique=False)
    op.create_index("ix_sources_region", "sources", ["region"], unique=False)
    op.create_index("ix_sources_region_city", "sources", ["region", "city"], unique=False)

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("prompt_name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("change_description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_prompt_versions"),
        sa.UniqueConstraint("prompt_name", "version", name="uq_prompt_versions_name_version"),
    )
    op.create_index("ix_prompt_versions_active", "prompt_versions", ["active"], unique=False)
    op.create_index(
        "ix_prompt_versions_content_hash", "prompt_versions", ["content_hash"], unique=False
    )
    op.create_index(
        "ix_prompt_versions_name_active",
        "prompt_versions",
        ["prompt_name", "active"],
        unique=False,
    )
    op.create_index(
        "ix_prompt_versions_prompt_name", "prompt_versions", ["prompt_name"], unique=False
    )

    op.create_table(
        "retrieval_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("vector_top_k", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("bm25_top_k", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("fusion_method", sa.String(length=64), nullable=False, server_default="rrf"),
        sa.Column("rrf_k", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("rerank_top_k", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "score_threshold", sa.Numeric(precision=7, scale=6), nullable=False, server_default="0"
        ),
        sa.Column("metadata_rules_json", _json_type(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("bm25_top_k > 0", name="ck_retrieval_configs_bm25_top_k_positive"),
        sa.CheckConstraint("rerank_top_k > 0", name="ck_retrieval_configs_rerank_top_k_positive"),
        sa.CheckConstraint("rrf_k > 0", name="ck_retrieval_configs_rrf_k_positive"),
        sa.CheckConstraint(
            "score_threshold >= 0 AND score_threshold <= 1",
            name="ck_retrieval_configs_score_threshold_range",
        ),
        sa.CheckConstraint("vector_top_k > 0", name="ck_retrieval_configs_vector_top_k_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_retrieval_configs"),
        sa.UniqueConstraint("name", "version", name="uq_retrieval_configs_name_version"),
    )
    op.create_index("ix_retrieval_configs_name", "retrieval_configs", ["name"], unique=False)
    op.create_index(
        "ix_retrieval_configs_name_created",
        "retrieval_configs",
        ["name", "created_at"],
        unique=False,
    )

    op.create_table(
        "evaluation_questions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("question_id", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("query_type", sa.String(length=32), nullable=False),
        sa.Column("expected_document_ids", _json_type(), nullable=False),
        sa.Column("expected_chunk_ids", _json_type(), nullable=False),
        sa.Column("expected_answer_points", _json_type(), nullable=False),
        sa.Column("expected_filters", _json_type(), nullable=False),
        sa.Column("should_refuse", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("difficulty", sa.String(length=32), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_questions"),
        sa.UniqueConstraint("question_id", name="uq_evaluation_questions_question_id"),
    )
    op.create_index(
        "ix_evaluation_questions_category", "evaluation_questions", ["category"], unique=False
    )
    op.create_index(
        "ix_evaluation_questions_difficulty", "evaluation_questions", ["difficulty"], unique=False
    )
    op.create_index(
        "ix_evaluation_questions_query_difficulty",
        "evaluation_questions",
        ["query_type", "difficulty"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_questions_query_type", "evaluation_questions", ["query_type"], unique=False
    )
    op.create_index(
        "ix_evaluation_questions_should_refuse",
        "evaluation_questions",
        ["should_refuse"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_questions_verified", "evaluation_questions", ["verified"], unique=False
    )
    op.create_index(
        "ix_evaluation_questions_verified_category",
        "evaluation_questions",
        ["verified", "category"],
        unique=False,
    )

    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("experiment_name", sa.String(length=255), nullable=False),
        sa.Column("experiment_type", sa.String(length=128), nullable=False),
        sa.Column("baseline_config_json", _json_type(), nullable=False),
        sa.Column("candidate_config_json", _json_type(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("artifact_path", sa.String(length=4096), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_experiments_finish_not_before_start",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_experiments"),
        sa.UniqueConstraint("experiment_name", name="uq_experiments_experiment_name"),
    )
    op.create_index(
        "ix_experiments_experiment_type", "experiments", ["experiment_type"], unique=False
    )
    op.create_index("ix_experiments_status", "experiments", ["status"], unique=False)
    op.create_index(
        "ix_experiments_status_created", "experiments", ["status", "created_at"], unique=False
    )

    op.create_table(
        "query_traces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("query_type", sa.String(length=32), nullable=False),
        sa.Column("parsed_filters_json", _json_type(), nullable=False),
        sa.Column("bm25_results_json", _json_type(), nullable=False),
        sa.Column("vector_results_json", _json_type(), nullable=False),
        sa.Column("fusion_results_json", _json_type(), nullable=False),
        sa.Column("rerank_results_json", _json_type(), nullable=False),
        sa.Column("final_context_json", _json_type(), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("citations_json", _json_type(), nullable=False),
        sa.Column("refusal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_usage_json", _json_type(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=18, scale=8), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("cost >= 0", name="ck_query_traces_cost_nonnegative"),
        sa.CheckConstraint("latency_ms >= 0", name="ck_query_traces_latency_ms_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_query_traces"),
        sa.UniqueConstraint("trace_id", name="uq_query_traces_trace_id"),
    )
    op.create_index("ix_query_traces_model_name", "query_traces", ["model_name"], unique=False)
    op.create_index(
        "ix_query_traces_prompt_version", "query_traces", ["prompt_version"], unique=False
    )
    op.create_index("ix_query_traces_query_type", "query_traces", ["query_type"], unique=False)
    op.create_index("ix_query_traces_refusal", "query_traces", ["refusal"], unique=False)
    op.create_index(
        "ix_query_traces_refusal_created",
        "query_traces",
        ["refusal", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_query_traces_type_created",
        "query_traces",
        ["query_type", "created_at"],
        unique=False,
    )

    op.create_table(
        "source_columns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("column_key", sa.String(length=128), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("column_url", sa.String(length=2048), nullable=False),
        sa.Column("parser_type", sa.String(length=64), nullable=False, server_default="html"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("request_interval_seconds", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("selectors_json", _json_type(), nullable=False),
        sa.Column("pagination_json", _json_type(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("max_pages > 0", name="ck_source_columns_max_pages_positive"),
        sa.CheckConstraint(
            "request_interval_seconds >= 0",
            name="ck_source_columns_request_interval_seconds_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_source_columns_source_id_sources",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_columns"),
        sa.UniqueConstraint("source_id", "column_key", name="uq_source_columns_source_column_key"),
    )
    op.create_index(
        "ix_source_columns_source_enabled",
        "source_columns",
        ["source_id", "enabled"],
        unique=False,
    )
    op.create_index("ix_source_columns_source_id", "source_columns", ["source_id"], unique=False)

    op.create_table(
        "crawl_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_column_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False, server_default="incremental"),
        sa.Column("trigger_type", sa.String(length=64), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("url_duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("semantic_duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "content_duplicate_count >= 0",
            name="ck_crawl_tasks_content_duplicate_count_nonnegative",
        ),
        sa.CheckConstraint(
            "discovered_count >= 0", name="ck_crawl_tasks_discovered_count_nonnegative"
        ),
        sa.CheckConstraint("failed_count >= 0", name="ck_crawl_tasks_failed_count_nonnegative"),
        sa.CheckConstraint("fetched_count >= 0", name="ck_crawl_tasks_fetched_count_nonnegative"),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_crawl_tasks_finish_not_before_start",
        ),
        sa.CheckConstraint("retry_count >= 0", name="ck_crawl_tasks_retry_count_nonnegative"),
        sa.CheckConstraint(
            "semantic_duplicate_count >= 0",
            name="ck_crawl_tasks_semantic_duplicate_count_nonnegative",
        ),
        sa.CheckConstraint("success_count >= 0", name="ck_crawl_tasks_success_count_nonnegative"),
        sa.CheckConstraint(
            "url_duplicate_count >= 0",
            name="ck_crawl_tasks_url_duplicate_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["source_column_id"],
            ["source_columns.id"],
            name="fk_crawl_tasks_source_column_id_source_columns",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_tasks"),
    )
    op.create_index(
        "ix_crawl_tasks_source_column_id", "crawl_tasks", ["source_column_id"], unique=False
    )
    op.create_index(
        "ix_crawl_tasks_source_status",
        "crawl_tasks",
        ["source_column_id", "status"],
        unique=False,
    )
    op.create_index("ix_crawl_tasks_status", "crawl_tasks", ["status"], unique=False)
    op.create_index(
        "ix_crawl_tasks_status_created", "crawl_tasks", ["status", "created_at"], unique=False
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("source_column_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("subtitle", sa.String(length=1024), nullable=True),
        sa.Column("source_url", sa.String(length=4096), nullable=False),
        sa.Column("canonical_url", sa.String(length=4096), nullable=True),
        sa.Column("publish_date", sa.Date(), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("issuing_authority", sa.String(length=512), nullable=True),
        sa.Column("document_number", sa.String(length=255), nullable=True),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("document_type", sa.String(length=128), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("simhash", sa.String(length=32), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("quality_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "rule_filter_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "llm_review_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "manual_review_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("final_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("index_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_document_id", sa.Integer(), nullable=True),
        sa.Column("duplicate_of_document_id", sa.Integer(), nullable=True),
        sa.Column("first_crawl_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_crawl_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "last_crawl_time IS NULL OR first_crawl_time IS NULL "
            "OR last_crawl_time >= first_crawl_time",
            name="ck_documents_last_crawl_not_before_first",
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="ck_documents_quality_score_range",
        ),
        sa.CheckConstraint("version > 0", name="ck_documents_version_positive"),
        sa.CheckConstraint("word_count >= 0", name="ck_documents_word_count_nonnegative"),
        sa.ForeignKeyConstraint(
            ["duplicate_of_document_id"],
            ["documents.id"],
            name="fk_documents_duplicate_of_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["parent_document_id"],
            ["documents.id"],
            name="fk_documents_parent_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_column_id"],
            ["source_columns.id"],
            name="fk_documents_source_column_id_source_columns",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_documents_source_id_sources",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("document_id", name="uq_documents_document_id"),
    )
    op.create_index("ix_documents_canonical_url", "documents", ["canonical_url"], unique=False)
    op.create_index("ix_documents_city", "documents", ["city"], unique=False)
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"], unique=False)
    op.create_index("ix_documents_document_number", "documents", ["document_number"], unique=False)
    op.create_index("ix_documents_document_type", "documents", ["document_type"], unique=False)
    op.create_index(
        "ix_documents_duplicate_of_document_id",
        "documents",
        ["duplicate_of_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_documents_final_index_status",
        "documents",
        ["final_status", "index_status"],
        unique=False,
    )
    op.create_index("ix_documents_final_status", "documents", ["final_status"], unique=False)
    op.create_index("ix_documents_index_status", "documents", ["index_status"], unique=False)
    op.create_index(
        "ix_documents_issuing_authority", "documents", ["issuing_authority"], unique=False
    )
    op.create_index("ix_documents_language", "documents", ["language"], unique=False)
    op.create_index(
        "ix_documents_llm_review_status", "documents", ["llm_review_status"], unique=False
    )
    op.create_index(
        "ix_documents_manual_review_status",
        "documents",
        ["manual_review_status"],
        unique=False,
    )
    op.create_index(
        "ix_documents_parent_document_id", "documents", ["parent_document_id"], unique=False
    )
    op.create_index("ix_documents_publish_date", "documents", ["publish_date"], unique=False)
    op.create_index("ix_documents_region", "documents", ["region"], unique=False)
    op.create_index(
        "ix_documents_region_type", "documents", ["region", "document_type"], unique=False
    )
    op.create_index(
        "ix_documents_review_statuses",
        "documents",
        ["rule_filter_status", "llm_review_status"],
        unique=False,
    )
    op.create_index(
        "ix_documents_rule_filter_status", "documents", ["rule_filter_status"], unique=False
    )
    op.create_index("ix_documents_simhash", "documents", ["simhash"], unique=False)
    op.create_index(
        "ix_documents_source_column_id", "documents", ["source_column_id"], unique=False
    )
    op.create_index("ix_documents_source_id", "documents", ["source_id"], unique=False)
    op.create_index(
        "ix_documents_source_publish_date",
        "documents",
        ["source_id", "publish_date"],
        unique=False,
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", _json_type(), nullable=False),
        sa.Column("changed_fields_json", _json_type(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("version > 0", name="ck_document_versions_version_positive"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_versions_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint("document_id", "version", name="uq_document_versions_document_version"),
    )
    op.create_index(
        "ix_document_versions_content_hash",
        "document_versions",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_document_versions_document_created",
        "document_versions",
        ["document_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_document_versions_document_id",
        "document_versions",
        ["document_id"],
        unique=False,
    )

    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("attachment_name", sa.String(length=1024), nullable=False),
        sa.Column("source_url", sa.String(length=4096), nullable=False),
        sa.Column("local_path", sa.String(length=4096), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("file_extension", sa.String(length=32), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("file_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "download_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("parse_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("parsed_text", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("requires_ocr", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "file_size IS NULL OR file_size >= 0",
            name="ck_attachments_file_size_nonnegative",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_attachments_page_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_attachments_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attachments"),
    )
    op.create_index(
        "ix_attachments_document_download",
        "attachments",
        ["document_id", "download_status"],
        unique=False,
    )
    op.create_index("ix_attachments_document_id", "attachments", ["document_id"], unique=False)
    op.create_index(
        "ix_attachments_document_parse",
        "attachments",
        ["document_id", "parse_status"],
        unique=False,
    )
    op.create_index(
        "ix_attachments_download_status", "attachments", ["download_status"], unique=False
    )
    op.create_index(
        "ix_attachments_file_extension", "attachments", ["file_extension"], unique=False
    )
    op.create_index("ix_attachments_file_hash", "attachments", ["file_hash"], unique=False)
    op.create_index("ix_attachments_mime_type", "attachments", ["mime_type"], unique=False)
    op.create_index("ix_attachments_parse_status", "attachments", ["parse_status"], unique=False)

    op.create_table(
        "document_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("review_type", sa.String(length=64), nullable=False),
        sa.Column("reviewer", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("quality_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("document_type", sa.String(length=128), nullable=True),
        sa.Column("topics_json", _json_type(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("reasons_json", _json_type(), nullable=False),
        sa.Column("extracted_fields_json", _json_type(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="ck_document_reviews_quality_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_reviews_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_reviews"),
    )
    op.create_index("ix_document_reviews_decision", "document_reviews", ["decision"], unique=False)
    op.create_index(
        "ix_document_reviews_decision_created",
        "document_reviews",
        ["decision", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_document_reviews_document_id", "document_reviews", ["document_id"], unique=False
    )
    op.create_index(
        "ix_document_reviews_document_type_created",
        "document_reviews",
        ["document_id", "review_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_document_reviews_review_type", "document_reviews", ["review_type"], unique=False
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chunk_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("attachment_id", sa.Integer(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.String(length=2048), nullable=True),
        sa.Column("section_title", sa.String(length=1024), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_version", sa.String(length=64), nullable=True),
        sa.Column("vector_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("char_count >= 0", name="ck_chunks_char_count_nonnegative"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_chunks_chunk_index_nonnegative"),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number > 0", name="ck_chunks_page_number_positive"
        ),
        sa.CheckConstraint("token_count >= 0", name="ck_chunks_token_count_nonnegative"),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_chunks_attachment_id_attachments",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_chunks_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
        sa.UniqueConstraint("chunk_id", name="uq_chunks_chunk_id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_chunk_index"),
    )
    op.create_index(
        "ix_chunks_attachment_chunk_index",
        "chunks",
        ["attachment_id", "chunk_index"],
        unique=False,
    )
    op.create_index("ix_chunks_attachment_id", "chunks", ["attachment_id"], unique=False)
    op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"], unique=False)
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"], unique=False)
    op.create_index(
        "ix_chunks_document_vector_status",
        "chunks",
        ["document_id", "vector_status"],
        unique=False,
    )
    op.create_index("ix_chunks_embedding_model", "chunks", ["embedding_model"], unique=False)
    op.create_index("ix_chunks_page_number", "chunks", ["page_number"], unique=False)
    op.create_index("ix_chunks_vector_status", "chunks", ["vector_status"], unique=False)

    op.create_table(
        "structured_knowledge",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_type", sa.String(length=128), nullable=False),
        sa.Column("field_name", sa.String(length=255), nullable=False),
        sa.Column("field_value_json", _json_type(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("evidence_chunk_id", sa.Integer(), nullable=True),
        sa.Column("extraction_model", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_structured_knowledge_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_structured_knowledge_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_chunk_id"],
            ["chunks.id"],
            name="fk_structured_knowledge_evidence_chunk_id_chunks",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_structured_knowledge"),
    )
    op.create_index(
        "ix_structured_knowledge_document_id",
        "structured_knowledge",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_structured_knowledge_document_type",
        "structured_knowledge",
        ["document_id", "knowledge_type"],
        unique=False,
    )
    op.create_index(
        "ix_structured_knowledge_evidence_chunk_id",
        "structured_knowledge",
        ["evidence_chunk_id"],
        unique=False,
    )
    op.create_index(
        "ix_structured_knowledge_field",
        "structured_knowledge",
        ["field_name", "verified"],
        unique=False,
    )
    op.create_index(
        "ix_structured_knowledge_field_name",
        "structured_knowledge",
        ["field_name"],
        unique=False,
    )
    op.create_index(
        "ix_structured_knowledge_knowledge_type",
        "structured_knowledge",
        ["knowledge_type"],
        unique=False,
    )
    op.create_index(
        "ix_structured_knowledge_verified",
        "structured_knowledge",
        ["verified"],
        unique=False,
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_name", sa.String(length=255), nullable=False),
        sa.Column("experiment_id", sa.Integer(), nullable=True),
        sa.Column("retrieval_version", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("rerank_model", sa.String(length=255), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recall_at_1", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("recall_at_5", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("recall_at_10", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("mrr", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("ndcg", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("citation_accuracy", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("refusal_accuracy", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("hallucination_rate", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("average_latency", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("p95_latency", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("average_cost", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("result_path", sa.String(length=4096), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "average_cost IS NULL OR average_cost >= 0",
            name="ck_evaluation_runs_average_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "average_latency IS NULL OR average_latency >= 0",
            name="ck_evaluation_runs_average_latency_nonnegative",
        ),
        sa.CheckConstraint(
            "citation_accuracy IS NULL OR (citation_accuracy >= 0 AND citation_accuracy <= 1)",
            name="ck_evaluation_runs_citation_accuracy_range",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_evaluation_runs_finish_not_before_start",
        ),
        sa.CheckConstraint(
            "hallucination_rate IS NULL OR (hallucination_rate >= 0 AND hallucination_rate <= 1)",
            name="ck_evaluation_runs_hallucination_rate_range",
        ),
        sa.CheckConstraint(
            "mrr IS NULL OR (mrr >= 0 AND mrr <= 1)",
            name="ck_evaluation_runs_mrr_range",
        ),
        sa.CheckConstraint(
            "ndcg IS NULL OR (ndcg >= 0 AND ndcg <= 1)",
            name="ck_evaluation_runs_ndcg_range",
        ),
        sa.CheckConstraint(
            "p95_latency IS NULL OR p95_latency >= 0",
            name="ck_evaluation_runs_p95_latency_nonnegative",
        ),
        sa.CheckConstraint(
            "question_count >= 0", name="ck_evaluation_runs_question_count_nonnegative"
        ),
        sa.CheckConstraint(
            "recall_at_1 IS NULL OR (recall_at_1 >= 0 AND recall_at_1 <= 1)",
            name="ck_evaluation_runs_recall_at_1_range",
        ),
        sa.CheckConstraint(
            "recall_at_10 IS NULL OR (recall_at_10 >= 0 AND recall_at_10 <= 1)",
            name="ck_evaluation_runs_recall_at_10_range",
        ),
        sa.CheckConstraint(
            "recall_at_5 IS NULL OR (recall_at_5 >= 0 AND recall_at_5 <= 1)",
            name="ck_evaluation_runs_recall_at_5_range",
        ),
        sa.CheckConstraint(
            "refusal_accuracy IS NULL OR (refusal_accuracy >= 0 AND refusal_accuracy <= 1)",
            name="ck_evaluation_runs_refusal_accuracy_range",
        ),
        sa.CheckConstraint("top_k > 0", name="ck_evaluation_runs_top_k_positive"),
        sa.ForeignKeyConstraint(
            ["experiment_id"],
            ["experiments.id"],
            name="fk_evaluation_runs_experiment_id_experiments",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluation_runs"),
    )
    op.create_index(
        "ix_evaluation_runs_experiment_created",
        "evaluation_runs",
        ["experiment_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_runs_experiment_id", "evaluation_runs", ["experiment_id"], unique=False
    )
    op.create_index(
        "ix_evaluation_runs_prompt_version", "evaluation_runs", ["prompt_version"], unique=False
    )
    op.create_index(
        "ix_evaluation_runs_retrieval_prompt",
        "evaluation_runs",
        ["retrieval_version", "prompt_version"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_runs_retrieval_version",
        "evaluation_runs",
        ["retrieval_version"],
        unique=False,
    )
    op.create_index("ix_evaluation_runs_run_name", "evaluation_runs", ["run_name"], unique=False)

    op.create_table(
        "user_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("feedback_type", sa.String(length=64), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("expected_document_id", sa.Integer(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "converted_to_evaluation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "rating IS NULL OR (rating >= 1 AND rating <= 5)",
            name="ck_user_feedback_rating_range",
        ),
        sa.ForeignKeyConstraint(
            ["expected_document_id"],
            ["documents.id"],
            name="fk_user_feedback_expected_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["trace_id"],
            ["query_traces.trace_id"],
            name="fk_user_feedback_trace_id_query_traces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_feedback"),
    )
    op.create_index(
        "ix_user_feedback_converted_to_evaluation",
        "user_feedback",
        ["converted_to_evaluation"],
        unique=False,
    )
    op.create_index(
        "ix_user_feedback_expected_document_id",
        "user_feedback",
        ["expected_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_feedback_feedback_type", "user_feedback", ["feedback_type"], unique=False
    )
    op.create_index("ix_user_feedback_resolved", "user_feedback", ["resolved"], unique=False)
    op.create_index(
        "ix_user_feedback_resolved_created",
        "user_feedback",
        ["resolved", "created_at"],
        unique=False,
    )
    op.create_index("ix_user_feedback_trace_id", "user_feedback", ["trace_id"], unique=False)
    op.create_index(
        "ix_user_feedback_type_created",
        "user_feedback",
        ["feedback_type", "created_at"],
        unique=False,
    )

    op.create_table(
        "data_lineage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lineage_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("crawl_task_id", sa.Integer(), nullable=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("document_version_id", sa.Integer(), nullable=True),
        sa.Column("attachment_id", sa.Integer(), nullable=True),
        sa.Column("chunk_id", sa.Integer(), nullable=True),
        sa.Column("vector_point_id", sa.String(length=255), nullable=True),
        sa.Column("evaluation_run_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["attachment_id"],
            ["attachments.id"],
            name="fk_data_lineage_attachment_id_attachments",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            name="fk_data_lineage_chunk_id_chunks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["crawl_task_id"],
            ["crawl_tasks.id"],
            name="fk_data_lineage_crawl_task_id_crawl_tasks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_data_lineage_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_data_lineage_document_version_id_document_versions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            name="fk_data_lineage_evaluation_run_id_evaluation_runs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_data_lineage_source_id_sources",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_lineage"),
        sa.UniqueConstraint("lineage_id", name="uq_data_lineage_lineage_id"),
    )
    op.create_index(
        "ix_data_lineage_attachment_id", "data_lineage", ["attachment_id"], unique=False
    )
    op.create_index("ix_data_lineage_chunk_id", "data_lineage", ["chunk_id"], unique=False)
    op.create_index(
        "ix_data_lineage_crawl_task_id", "data_lineage", ["crawl_task_id"], unique=False
    )
    op.create_index(
        "ix_data_lineage_document_chunk",
        "data_lineage",
        ["document_id", "chunk_id"],
        unique=False,
    )
    op.create_index("ix_data_lineage_document_id", "data_lineage", ["document_id"], unique=False)
    op.create_index(
        "ix_data_lineage_document_version_id",
        "data_lineage",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_data_lineage_evaluation",
        "data_lineage",
        ["evaluation_run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_data_lineage_evaluation_run_id",
        "data_lineage",
        ["evaluation_run_id"],
        unique=False,
    )
    op.create_index("ix_data_lineage_source_id", "data_lineage", ["source_id"], unique=False)
    op.create_index(
        "ix_data_lineage_source_crawl",
        "data_lineage",
        ["source_id", "crawl_task_id"],
        unique=False,
    )
    op.create_index(
        "ix_data_lineage_vector_point_id", "data_lineage", ["vector_point_id"], unique=False
    )


def downgrade() -> None:
    op.drop_table("data_lineage")
    op.drop_table("user_feedback")
    op.drop_table("evaluation_runs")
    op.drop_table("structured_knowledge")
    op.drop_table("chunks")
    op.drop_table("document_reviews")
    op.drop_table("attachments")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("crawl_tasks")
    op.drop_table("source_columns")
    op.drop_table("query_traces")
    op.drop_table("experiments")
    op.drop_table("evaluation_questions")
    op.drop_table("retrieval_configs")
    op.drop_table("prompt_versions")
    op.drop_table("sources")
    op.drop_table("users")
