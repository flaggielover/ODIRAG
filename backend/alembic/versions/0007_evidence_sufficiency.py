"""persist evidence sufficiency decisions

Revision ID: 0007_evidence_sufficiency
Revises: 0006_coze_task_operations
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_evidence_sufficiency"
down_revision: str | None = "0006_coze_task_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "query_traces",
        sa.Column(
            "evidence_decision_json",
            _json_type(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("query_traces", "evidence_decision_json")
