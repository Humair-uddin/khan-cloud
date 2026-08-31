"""gaming runtime recovery v1

Revision ID: c3a009f10001
Revises: c2a009f10001
"""

from alembic import op
import sqlalchemy as sa

revision = "c3a009f10001"
down_revision = "c2a009f10001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gaming_sessions",
        sa.Column(
            "runtime_health_failure_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "gaming_sessions",
        sa.Column(
            "runtime_health_last_checked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "gaming_sessions",
        sa.Column(
            "runtime_health_last_failure_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "gaming_sessions",
        sa.Column(
            "runtime_recovery_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    for column in (
        "runtime_recovery_count",
        "runtime_health_last_failure_at",
        "runtime_health_last_checked_at",
        "runtime_health_failure_count",
    ):
        op.drop_column("gaming_sessions", column)
