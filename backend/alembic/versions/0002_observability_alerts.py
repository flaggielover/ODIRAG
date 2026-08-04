"""add prompt snapshots and persistent alerts

Revision ID: 0002_observability_alerts
Revises: 0001_core_schema
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_observability_alerts"
down_revision: str | None = "0001_core_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "query_traces",
        sa.Column(
            "prompt_snapshot_json",
            _json_type(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_key", sa.String(length=255), nullable=False),
        sa.Column("alert_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="warning"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("observed_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("threshold_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("details_json", _json_type(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("occurrence_count > 0", name="ck_alerts_occurrence_count_positive"),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'high', 'critical')",
            name="ck_alerts_severity_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name="ck_alerts_status_allowed",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_alerts"),
        sa.UniqueConstraint("alert_key", name="uq_alerts_alert_key"),
    )
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"], unique=False)
    op.create_index("ix_alerts_component", "alerts", ["component"], unique=False)
    op.create_index("ix_alerts_severity", "alerts", ["severity"], unique=False)
    op.create_index("ix_alerts_status", "alerts", ["status"], unique=False)
    op.create_index("ix_alerts_status_severity", "alerts", ["status", "severity"], unique=False)
    op.create_index(
        "ix_alerts_type_last_seen", "alerts", ["alert_type", "last_seen_at"], unique=False
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_column("query_traces", "prompt_snapshot_json")
