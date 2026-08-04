"""add crawl document uniqueness

Revision ID: 0003_crawl_reliability
Revises: 0002_observability_alerts
Create Date: 2026-08-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_crawl_reliability"
down_revision: str | None = "0002_observability_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.create_unique_constraint(
            "uq_documents_source_column_canonical_url",
            ["source_column_id", "canonical_url"],
        )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_constraint(
            "uq_documents_source_column_canonical_url",
            type_="unique",
        )
