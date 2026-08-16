"""add attachment download and extraction audit fields

Revision ID: 0011_attachment_download_audit
Revises: 0010_query_trace_stage_timings
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_attachment_download_audit"
down_revision: str | None = "0010_query_trace_stage_timings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("attachments", sa.Column("download_http_status", sa.Integer(), nullable=True))
    op.add_column(
        "attachments", sa.Column("download_final_url", sa.String(length=4096), nullable=True)
    )
    op.add_column(
        "attachments", sa.Column("download_error_code", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "attachments",
        sa.Column(
            "download_retryable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "attachments", sa.Column("extraction_method", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "attachments", sa.Column("type_detection_source", sa.String(length=64), nullable=True)
    )
    op.create_index(
        op.f("ix_attachments_download_error_code"),
        "attachments",
        ["download_error_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_attachments_download_error_code"), table_name="attachments")
    op.drop_column("attachments", "type_detection_source")
    op.drop_column("attachments", "extraction_method")
    op.drop_column("attachments", "download_retryable")
    op.drop_column("attachments", "download_error_code")
    op.drop_column("attachments", "download_final_url")
    op.drop_column("attachments", "download_http_status")
