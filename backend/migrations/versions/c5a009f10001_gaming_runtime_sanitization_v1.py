"""gaming runtime sanitization v1

Revision ID: c5a009f10001
Revises: c4a009f10001
"""
from alembic import op
import sqlalchemy as sa

revision = "c5a009f10001"
down_revision = "c4a009f10001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("gaming_sessions", sa.Column("sanitization_state", sa.String(length=30), nullable=False, server_default=""))
    op.add_column("gaming_sessions", sa.Column("sanitization_attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("gaming_sessions", sa.Column("sanitization_last_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_sessions", sa.Column("sanitized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_sessions", sa.Column("quarantine_reason", sa.String(length=160), nullable=False, server_default=""))
    op.create_index("ix_gaming_sessions_sanitization_state", "gaming_sessions", ["sanitization_state"], unique=False)
    op.alter_column("gaming_sessions", "sanitization_state", server_default=None)
    op.alter_column("gaming_sessions", "sanitization_attempt_count", server_default=None)
    op.alter_column("gaming_sessions", "quarantine_reason", server_default=None)

def downgrade() -> None:
    op.drop_index("ix_gaming_sessions_sanitization_state", table_name="gaming_sessions")
    op.drop_column("gaming_sessions", "quarantine_reason")
    op.drop_column("gaming_sessions", "sanitized_at")
    op.drop_column("gaming_sessions", "sanitization_last_checked_at")
    op.drop_column("gaming_sessions", "sanitization_attempt_count")
    op.drop_column("gaming_sessions", "sanitization_state")
