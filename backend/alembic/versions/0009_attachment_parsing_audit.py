"""add auditable attachment parsing outcomes

Revision ID: 0009_attachment_parsing_audit
Revises: 0008_rerank_observability
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_attachment_parsing_audit"
down_revision: str | None = "0008_rerank_observability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("file_type", sa.String(length=32), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "attachments",
        sa.Column("extracted_text_length", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("attachments", sa.Column("parser", sa.String(length=64), nullable=True))
    op.add_column(
        "attachments",
        sa.Column(
            "ocr_status",
            sa.String(length=32),
            nullable=False,
            server_default="not_required",
        ),
    )
    op.add_column("attachments", sa.Column("ocr_provider", sa.String(length=64), nullable=True))
    op.add_column("attachments", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column(
        "attachments",
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "attachments",
        sa.Column("parse_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_check_constraint(
            op.f("ck_attachments_extracted_text_length_nonnegative"),
            "attachments",
            "extracted_text_length >= 0",
        )
    op.create_index(op.f("ix_attachments_file_type"), "attachments", ["file_type"], unique=False)
    op.create_index(op.f("ix_attachments_ocr_status"), "attachments", ["ocr_status"], unique=False)
    op.create_index(op.f("ix_attachments_error_code"), "attachments", ["error_code"], unique=False)
    op.execute(
        sa.text(
            "UPDATE attachments "
            "SET file_type = COALESCE(NULLIF(file_extension, ''), 'unknown'), "
            "extracted_text_length = COALESCE(length(parsed_text), 0), "
            "parser = CASE WHEN parse_status = 'completed' THEN 'legacy' ELSE parser END, "
            "parse_status = CASE WHEN parse_status = 'completed' "
            "THEN 'parsed' ELSE parse_status END"
        )
    )
    op.create_table(
        "document_metadata_corrections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="unresolved"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_source", sa.String(length=1024), nullable=True),
        sa.Column("correction_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_metadata_corrections_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_metadata_corrections")),
        sa.CheckConstraint(
            "status IN ('unresolved', 'applied', 'rejected')",
            name=op.f("ck_document_metadata_corrections_status_valid"),
        ),
        sa.UniqueConstraint("correction_key", name="uq_document_metadata_corrections_key"),
    )
    op.create_index(
        op.f("ix_document_metadata_corrections_document"),
        "document_metadata_corrections",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_document_metadata_corrections_status"),
        "document_metadata_corrections",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_document_metadata_corrections_status"),
        table_name="document_metadata_corrections",
    )
    op.drop_index(
        op.f("ix_document_metadata_corrections_document"),
        table_name="document_metadata_corrections",
    )
    op.drop_table("document_metadata_corrections")
    op.execute(
        sa.text("UPDATE attachments SET parse_status = 'completed' WHERE parse_status = 'parsed'")
    )
    op.drop_index(op.f("ix_attachments_error_code"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_ocr_status"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_file_type"), table_name="attachments")
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint(
            op.f("ck_attachments_extracted_text_length_nonnegative"),
            "attachments",
            type_="check",
        )
    op.drop_column("attachments", "parse_attempted_at")
    op.drop_column("attachments", "retryable")
    op.drop_column("attachments", "error_code")
    op.drop_column("attachments", "ocr_provider")
    op.drop_column("attachments", "ocr_status")
    op.drop_column("attachments", "parser")
    op.drop_column("attachments", "extracted_text_length")
    op.drop_column("attachments", "file_type")
