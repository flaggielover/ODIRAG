"""add content-gap driven source discovery entities

Revision ID: 0004_source_discovery
Revises: 0003_crawl_reliability
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_source_discovery"
down_revision: str | None = "0003_crawl_reliability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    json_type = _json_type()
    op.create_table(
        "source_discovery_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("organization_level", sa.String(length=64), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("required_source_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("required_document_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("existing_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("existing_document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gap_detected", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("gap_evidence_json", json_type, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column(
            "discovery_provider", sa.String(length=64), nullable=False, server_default="brave"
        ),
        sa.Column("max_candidates", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'no_gap', 'awaiting_approval', 'activated', 'failed')",
            name="ck_source_discovery_runs_source_discovery_run_status_allowed",
        ),
        sa.CheckConstraint(
            "required_source_count > 0",
            name="ck_source_discovery_runs_source_discovery_required_sources_positive",
        ),
        sa.CheckConstraint(
            "required_document_count >= 0",
            name="ck_source_discovery_runs_source_discovery_required_documents_nonnegative",
        ),
        sa.CheckConstraint(
            "max_candidates > 0",
            name="ck_source_discovery_runs_source_discovery_max_candidates_positive",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_source_discovery_runs_source_discovery_attempt_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_discovery_runs"),
    )
    op.create_index(
        "ix_source_discovery_runs_status_created",
        "source_discovery_runs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_source_discovery_runs_topic", "source_discovery_runs", ["topic"]
    )
    op.create_index(
        "ix_source_discovery_runs_topic_region",
        "source_discovery_runs",
        ["topic", "region"],
    )
    op.create_index(
        "ix_source_discovery_runs_region", "source_discovery_runs", ["region"]
    )
    op.create_index(
        "ix_source_discovery_runs_organization_level",
        "source_discovery_runs",
        ["organization_level"],
    )
    op.create_index(
        "ix_source_discovery_runs_gap_detected",
        "source_discovery_runs",
        ["gap_detected"],
    )
    op.create_index(
        "ix_source_discovery_runs_status",
        "source_discovery_runs",
        ["status"],
    )
    op.create_index(
        "ix_source_discovery_runs_created_by",
        "source_discovery_runs",
        ["created_by"],
    )

    op.create_table(
        "source_candidates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("canonical_homepage_url", sa.String(length=4096), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("search_rank", sa.Integer(), nullable=True),
        sa.Column("discovery_provider", sa.String(length=64), nullable=False),
        sa.Column("discovery_query", sa.Text(), nullable=False),
        sa.Column("official_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("official_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("official_evidence_json", json_type, nullable=False),
        sa.Column("validation_status_code", sa.Integer(), nullable=True),
        sa.Column("validation_final_url", sa.String(length=4096), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="discovered"),
        sa.Column("quality_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("quality_breakdown_json", json_type, nullable=False),
        sa.Column("trial_column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_average_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "official_score IS NULL OR (official_score >= 0 AND official_score <= 1)",
            name="ck_source_candidates_source_candidate_official_score_range",
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="ck_source_candidates_source_candidate_quality_score_range",
        ),
        sa.CheckConstraint(
            "status IN ('discovered', 'validation_failed', 'validated', 'columns_discovered', 'trial_crawled', 'pending_approval', 'approved', 'rejected', 'activating', 'activated', 'failed')",
            name="ck_source_candidates_source_candidate_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["source_discovery_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_source_candidates"),
        sa.UniqueConstraint(
            "run_id", "canonical_homepage_url", name="uq_source_candidates_run_homepage"
        ),
    )
    op.create_index(
        "ix_source_candidates_run_status", "source_candidates", ["run_id", "status"]
    )
    op.create_index(
        "ix_source_candidates_quality", "source_candidates", ["quality_score"]
    )
    op.create_index("ix_source_candidates_run_id", "source_candidates", ["run_id"])
    op.create_index("ix_source_candidates_domain", "source_candidates", ["domain"])
    op.create_index(
        "ix_source_candidates_official_status", "source_candidates", ["official_status"]
    )
    op.create_index("ix_source_candidates_status", "source_candidates", ["status"])
    op.create_index("ix_source_candidates_source_id", "source_candidates", ["source_id"])

    op.create_table(
        "source_candidate_columns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("column_key", sa.String(length=128), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("column_url", sa.String(length=4096), nullable=False),
        sa.Column("parser_type", sa.String(length=64), nullable=False, server_default="html"),
        sa.Column("selectors_json", json_type, nullable=False),
        sa.Column("pagination_json", json_type, nullable=False),
        sa.Column("discovery_evidence_json", json_type, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="discovered"),
        sa.Column("trial_discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_average_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="ck_source_candidate_columns_source_candidate_column_quality_range",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["source_candidates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_candidate_columns"),
        sa.UniqueConstraint("candidate_id", "column_url", name="uq_source_candidate_columns_url"),
    )
    op.create_index(
        "ix_source_candidate_columns_candidate_status",
        "source_candidate_columns",
        ["candidate_id", "status"],
    )
    op.create_index(
        "ix_source_candidate_columns_candidate_id",
        "source_candidate_columns",
        ["candidate_id"],
    )
    op.create_index(
        "ix_source_candidate_columns_status",
        "source_candidate_columns",
        ["status"],
    )

    op.create_table(
        "source_discovery_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["run_id"], ["source_discovery_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["source_candidates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_discovery_events"),
    )
    op.create_index(
        "ix_source_discovery_events_run_created",
        "source_discovery_events",
        ["run_id", "created_at"],
    )
    op.create_index(
        "ix_source_discovery_events_candidate_created",
        "source_discovery_events",
        ["candidate_id", "created_at"],
    )
    op.create_index(
        "ix_source_discovery_events_stage",
        "source_discovery_events",
        ["stage", "created_at"],
    )
    op.create_index("ix_source_discovery_events_run_id", "source_discovery_events", ["run_id"])
    op.create_index(
        "ix_source_discovery_events_candidate_id", "source_discovery_events", ["candidate_id"]
    )


def downgrade() -> None:
    op.drop_table("source_discovery_events")
    op.drop_table("source_candidate_columns")
    op.drop_table("source_candidates")
    op.drop_table("source_discovery_runs")
