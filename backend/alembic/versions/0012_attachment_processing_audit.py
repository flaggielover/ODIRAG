"""add attachment parser and OCR processing provenance

Revision ID: 0012_attachment_processing_audit
Revises: 0011_attachment_download_audit
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_attachment_processing_audit"
down_revision: str | None = "0011_attachment_download_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("attachments", sa.Column("parser_version", sa.String(length=64), nullable=True))
    op.add_column(
        "attachments", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("attachments", sa.Column("ocr_version", sa.String(length=64), nullable=True))
    op.add_column("attachments", sa.Column("ocr_page_count", sa.Integer(), nullable=True))
    op.add_column("attachments", sa.Column("ocr_text_length", sa.Integer(), nullable=True))
    op.add_column("attachments", sa.Column("ocr_latency_ms", sa.Integer(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_check_constraint(
            op.f("ck_attachments_ocr_page_count_nonnegative"),
            "attachments",
            "ocr_page_count IS NULL OR ocr_page_count >= 0",
        )
        op.create_check_constraint(
            op.f("ck_attachments_ocr_text_length_nonnegative"),
            "attachments",
            "ocr_text_length IS NULL OR ocr_text_length >= 0",
        )
        op.create_check_constraint(
            op.f("ck_attachments_ocr_latency_ms_nonnegative"),
            "attachments",
            "ocr_latency_ms IS NULL OR ocr_latency_ms >= 0",
        )
    op.create_index(
        op.f("ix_attachments_processed_at"), "attachments", ["processed_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_attachments_processed_at"), table_name="attachments")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint(
            op.f("ck_attachments_ocr_latency_ms_nonnegative"),
            "attachments",
            type_="check",
        )
        op.drop_constraint(
            op.f("ck_attachments_ocr_text_length_nonnegative"),
            "attachments",
            type_="check",
        )
        op.drop_constraint(
            op.f("ck_attachments_ocr_page_count_nonnegative"),
            "attachments",
            type_="check",
        )
    op.drop_column("attachments", "ocr_latency_ms")
    op.drop_column("attachments", "ocr_text_length")
    op.drop_column("attachments", "ocr_page_count")
    op.drop_column("attachments", "ocr_version")
    op.drop_column("attachments", "processed_at")
    op.drop_column("attachments", "parser_version")
