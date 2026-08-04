"""add Coze crawl provider and invocation audit

Revision ID: 0005_coze_crawl_provider
Revises: 0004_source_discovery
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_coze_crawl_provider"
down_revision: str | None = "0004_source_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(
            sa.Column("crawl_provider", sa.String(length=32), nullable=False, server_default="coze")
        )
        batch_op.add_column(sa.Column("last_coze_status", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("last_coze_article_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_coze_error", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            "ck_sources_crawl_provider_allowed",
            "crawl_provider IN ('coze', 'local', 'playwright')",
        )
        batch_op.create_index("ix_sources_crawl_provider", ["crawl_provider"])

    with op.batch_alter_table("crawl_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("crawl_provider", sa.String(length=32), nullable=False, server_default="coze")
        )
        batch_op.add_column(sa.Column("provider_contract", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("provider_task_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("provider_status", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("provider_error_code", sa.String(length=128), nullable=True))
        batch_op.add_column(
            sa.Column("max_articles", sa.Integer(), nullable=False, server_default="5")
        )
        batch_op.add_column(
            sa.Column("max_pages", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.create_check_constraint(
            "ck_crawl_tasks_crawl_provider_allowed",
            "crawl_provider IN ('coze', 'local', 'playwright')",
        )
        batch_op.create_index("ix_crawl_tasks_crawl_provider", ["crawl_provider"])
        batch_op.create_index("ix_crawl_tasks_provider_task_id", ["provider_task_id"])

    op.create_table(
        "coze_invocations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crawl_task_id", sa.Integer(), nullable=False),
        sa.Column("contract", sa.String(length=64), nullable=False),
        sa.Column("endpoint_url", sa.String(length=2048), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("request_json", _json_type(), nullable=False),
        sa.Column("raw_response_json", _json_type(), nullable=True),
        sa.Column("normalized_response_json", _json_type(), nullable=True),
        sa.Column("http_status_code", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("token_usage_json", _json_type(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("attempt_count > 0", name="ck_coze_invocations_attempt_count_positive"),
        sa.CheckConstraint("retry_count >= 0", name="ck_coze_invocations_retry_count_nonnegative"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_coze_invocations_duration_nonnegative",
        ),
        sa.ForeignKeyConstraint(["crawl_task_id"], ["crawl_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_coze_invocations"),
    )
    op.create_index("ix_coze_invocations_crawl_task_id", "coze_invocations", ["crawl_task_id"])
    op.create_index(
        "ix_coze_invocations_task_created", "coze_invocations", ["crawl_task_id", "created_at"]
    )
    op.create_index(
        "ix_coze_invocations_status_created", "coze_invocations", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("coze_invocations")
    with op.batch_alter_table("crawl_tasks") as batch_op:
        batch_op.drop_index("ix_crawl_tasks_provider_task_id")
        batch_op.drop_index("ix_crawl_tasks_crawl_provider")
        batch_op.drop_constraint("ck_crawl_tasks_crawl_provider_allowed", type_="check")
        batch_op.drop_column("provider_error_code")
        batch_op.drop_column("max_pages")
        batch_op.drop_column("max_articles")
        batch_op.drop_column("provider_status")
        batch_op.drop_column("provider_task_id")
        batch_op.drop_column("provider_contract")
        batch_op.drop_column("crawl_provider")
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_index("ix_sources_crawl_provider")
        batch_op.drop_constraint("ck_sources_crawl_provider_allowed", type_="check")
        batch_op.drop_column("last_coze_error")
        batch_op.drop_column("last_coze_article_count")
        batch_op.drop_column("last_coze_status")
        batch_op.drop_column("crawl_provider")
