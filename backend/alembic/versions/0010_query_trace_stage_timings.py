"""persist retrieval stage timings on query traces

Revision ID: 0010_query_trace_stage_timings
Revises: 0009_attachment_parsing_audit
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_query_trace_stage_timings"
down_revision: str | None = "0009_attachment_parsing_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "query_traces",
        sa.Column(
            "stage_timings_json",
            _json_type(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("query_traces", "stage_timings_json")
