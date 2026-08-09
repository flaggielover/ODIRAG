"""persist rerank execution metadata

Revision ID: 0008_rerank_observability
Revises: 0007_evidence_sufficiency
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_rerank_observability"
down_revision: str | None = "0007_evidence_sufficiency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "query_traces",
        sa.Column(
            "rerank_metadata_json",
            _json_type(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("query_traces", "rerank_metadata_json")
