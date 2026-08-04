"""add Coze task operation and failed URL state

Revision ID: 0006_coze_task_operations
Revises: 0005_coze_crawl_provider
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_coze_task_operations"
down_revision: str | None = "0005_coze_crawl_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(
            sa.Column(
                "coze_contract_mode",
                sa.String(length=64),
                nullable=False,
                server_default="batch_crawl",
            )
        )
        batch_op.add_column(sa.Column("last_coze_test_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("last_successful_crawl_at", sa.DateTime(timezone=True)))
        batch_op.create_check_constraint(
            "ck_sources_coze_contract_mode_allowed",
            "coze_contract_mode IN ('legacy_single_article', 'batch_crawl')",
        )

    with op.batch_alter_table("crawl_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="coze")
        )
        batch_op.add_column(
            sa.Column(
                "contract_mode",
                sa.String(length=64),
                nullable=False,
                server_default="batch_crawl",
            )
        )
        batch_op.add_column(
            sa.Column(
                "current_stage", sa.String(length=64), nullable=False, server_default="pending"
            )
        )
        batch_op.add_column(sa.Column("provider_error_message", sa.Text()))
        batch_op.add_column(sa.Column("coze_execution_id", sa.String(length=255)))
        batch_op.add_column(
            sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("pending_review_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(timezone=True)))
        batch_op.create_index("ix_crawl_tasks_provider", ["provider"])
        batch_op.create_index("ix_crawl_tasks_current_stage", ["current_stage"])
        batch_op.create_index("ix_crawl_tasks_next_retry_at", ["next_retry_at"])
        batch_op.create_index("ix_crawl_tasks_coze_execution_id", ["coze_execution_id"])
        batch_op.create_check_constraint(
            "ck_crawl_tasks_provider_allowed",
            "provider IN ('coze', 'local', 'playwright')",
        )
        batch_op.create_check_constraint(
            "ck_crawl_tasks_contract_mode_allowed",
            "contract_mode IN ('legacy_single_article', 'batch_crawl')",
        )
        batch_op.create_check_constraint(
            "ck_crawl_tasks_accepted_count_nonnegative", "accepted_count >= 0"
        )
        batch_op.create_check_constraint(
            "ck_crawl_tasks_rejected_count_nonnegative", "rejected_count >= 0"
        )
        batch_op.create_check_constraint(
            "ck_crawl_tasks_pending_review_count_nonnegative", "pending_review_count >= 0"
        )

    op.execute(
        "UPDATE crawl_tasks SET provider = crawl_provider, "
        "contract_mode = COALESCE(provider_contract, 'batch_crawl'), "
        "current_stage = status, accepted_count = success_count, "
        "provider_error_message = error_message, completed_at = finished_at"
    )

    with op.batch_alter_table("coze_invocations") as batch_op:
        batch_op.add_column(sa.Column("source_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("deployment_identifier", sa.String(length=255), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_coze_invocations_source_id_sources",
            "sources",
            ["source_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_coze_invocations_source_id", ["source_id"])
    op.execute(
        "UPDATE coze_invocations SET source_id = ("
        "SELECT source_columns.source_id FROM crawl_tasks "
        "JOIN source_columns ON source_columns.id = crawl_tasks.source_column_id "
        "WHERE crawl_tasks.id = coze_invocations.crawl_task_id), "
        "endpoint_url = 'legacy-record', deployment_identifier = 'legacy-record'"
    )
    with op.batch_alter_table("coze_invocations") as batch_op:
        batch_op.alter_column("source_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column(
            "deployment_identifier", existing_type=sa.String(length=255), nullable=False
        )

    op.create_table(
        "crawl_task_failures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("crawl_task_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=4096), nullable=False),
        sa.Column("stage", sa.String(length=128), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'queued', 'retrying', 'succeeded', 'failed', 'skipped')",
            name="ck_crawl_task_failures_status_allowed",
        ),
        sa.CheckConstraint(
            "retry_count >= 0", name="ck_crawl_task_failures_retry_count_nonnegative"
        ),
        sa.ForeignKeyConstraint(["crawl_task_id"], ["crawl_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_crawl_task_failures"),
        sa.UniqueConstraint(
            "crawl_task_id",
            "url",
            "stage",
            "error_code",
            name="uq_crawl_task_failures_identity",
        ),
    )
    op.create_index(
        "ix_crawl_task_failures_crawl_task_id", "crawl_task_failures", ["crawl_task_id"]
    )
    op.create_index("ix_crawl_task_failures_retryable", "crawl_task_failures", ["retryable"])
    op.create_index("ix_crawl_task_failures_status", "crawl_task_failures", ["status"])
    op.create_index(
        "ix_crawl_task_failures_next_retry_at", "crawl_task_failures", ["next_retry_at"]
    )
    op.create_index(
        "ix_crawl_task_failures_task_status", "crawl_task_failures", ["crawl_task_id", "status"]
    )
    op.create_index(
        "ix_crawl_task_failures_retry", "crawl_task_failures", ["retryable", "next_retry_at"]
    )


def downgrade() -> None:
    op.drop_table("crawl_task_failures")
    with op.batch_alter_table("coze_invocations") as batch_op:
        batch_op.drop_index("ix_coze_invocations_source_id")
        batch_op.drop_constraint("fk_coze_invocations_source_id_sources", type_="foreignkey")
        batch_op.drop_column("deployment_identifier")
        batch_op.drop_column("source_id")
    with op.batch_alter_table("crawl_tasks") as batch_op:
        batch_op.drop_constraint("ck_crawl_tasks_provider_allowed", type_="check")
        batch_op.drop_constraint("ck_crawl_tasks_pending_review_count_nonnegative", type_="check")
        batch_op.drop_constraint("ck_crawl_tasks_rejected_count_nonnegative", type_="check")
        batch_op.drop_constraint("ck_crawl_tasks_accepted_count_nonnegative", type_="check")
        batch_op.drop_constraint("ck_crawl_tasks_contract_mode_allowed", type_="check")
        batch_op.drop_index("ix_crawl_tasks_coze_execution_id")
        batch_op.drop_index("ix_crawl_tasks_next_retry_at")
        batch_op.drop_index("ix_crawl_tasks_current_stage")
        batch_op.drop_index("ix_crawl_tasks_provider")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("next_retry_at")
        batch_op.drop_column("pending_review_count")
        batch_op.drop_column("rejected_count")
        batch_op.drop_column("accepted_count")
        batch_op.drop_column("provider_error_message")
        batch_op.drop_column("coze_execution_id")
        batch_op.drop_column("current_stage")
        batch_op.drop_column("contract_mode")
        batch_op.drop_column("provider")
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_constraint("ck_sources_coze_contract_mode_allowed", type_="check")
        batch_op.drop_column("last_successful_crawl_at")
        batch_op.drop_column("last_coze_test_at")
        batch_op.drop_column("coze_contract_mode")
