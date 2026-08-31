"""gaming quarantine recovery v1

Revision ID: c6a009f10001
Revises: c5a009f10001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c6a009f10001"
down_revision = "c5a009f10001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gaming_sessions", sa.Column("quarantine_recovery_state", sa.String(length=30), nullable=False, server_default=""))
    op.add_column("gaming_sessions", sa.Column("quarantine_recovery_attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("gaming_sessions", sa.Column("quarantine_recovery_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_sessions", sa.Column("quarantine_recovery_last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_sessions", sa.Column("quarantine_recovery_last_source", sa.String(length=30), nullable=False, server_default=""))
    op.add_column("gaming_sessions", sa.Column("quarantine_recovery_last_message", sa.String(length=500), nullable=False, server_default=""))
    op.add_column("gaming_sessions", sa.Column("quarantine_recovery_last_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("gaming_sessions", sa.Column("quarantine_recovered_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_gaming_sessions_quarantine_recovery_state", "gaming_sessions", ["quarantine_recovery_state"], unique=False)

    for column in (
        "quarantine_recovery_state",
        "quarantine_recovery_attempt_count",
        "quarantine_recovery_last_source",
        "quarantine_recovery_last_message",
        "quarantine_recovery_last_evidence",
    ):
        op.alter_column("gaming_sessions", column, server_default=None)


def downgrade() -> None:
    op.drop_index("ix_gaming_sessions_quarantine_recovery_state", table_name="gaming_sessions")
    op.drop_column("gaming_sessions", "quarantine_recovered_at")
    op.drop_column("gaming_sessions", "quarantine_recovery_last_evidence")
    op.drop_column("gaming_sessions", "quarantine_recovery_last_message")
    op.drop_column("gaming_sessions", "quarantine_recovery_last_source")
    op.drop_column("gaming_sessions", "quarantine_recovery_last_attempt_at")
    op.drop_column("gaming_sessions", "quarantine_recovery_requested_at")
    op.drop_column("gaming_sessions", "quarantine_recovery_attempt_count")
    op.drop_column("gaming_sessions", "quarantine_recovery_state")
