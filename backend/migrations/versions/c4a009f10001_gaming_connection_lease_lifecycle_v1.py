"""gaming connection lease lifecycle v1

Revision ID: c4a009f10001
Revises: c3a009f10001
"""
from alembic import op
import sqlalchemy as sa

revision = "c4a009f10001"
down_revision = "c3a009f10001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gaming_connection_leases", sa.Column("connection_token_hash", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("gaming_connection_leases", sa.Column("connection_token_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_connection_leases", sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_connection_leases", sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_connection_leases", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_connection_leases", sa.Column("reconnect_grace_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_connection_leases", sa.Column("reconnect_grace_seconds", sa.Integer(), nullable=False, server_default="120"))
    op.add_column("gaming_connection_leases", sa.Column("token_generation", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("gaming_connection_leases", sa.Column("revoked_reason", sa.String(length=80), nullable=False, server_default=""))
    op.create_index("ix_gaming_connection_leases_connection_token_expires_at", "gaming_connection_leases", ["connection_token_expires_at"], unique=False)
    op.create_index("ix_gaming_connection_leases_last_seen_at", "gaming_connection_leases", ["last_seen_at"], unique=False)
    op.create_index("ix_gaming_connection_leases_reconnect_grace_expires_at", "gaming_connection_leases", ["reconnect_grace_expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gaming_connection_leases_reconnect_grace_expires_at", table_name="gaming_connection_leases")
    op.drop_index("ix_gaming_connection_leases_last_seen_at", table_name="gaming_connection_leases")
    op.drop_index("ix_gaming_connection_leases_connection_token_expires_at", table_name="gaming_connection_leases")
    op.drop_column("gaming_connection_leases", "revoked_reason")
    op.drop_column("gaming_connection_leases", "token_generation")
    op.drop_column("gaming_connection_leases", "reconnect_grace_seconds")
    op.drop_column("gaming_connection_leases", "reconnect_grace_expires_at")
    op.drop_column("gaming_connection_leases", "last_seen_at")
    op.drop_column("gaming_connection_leases", "disconnected_at")
    op.drop_column("gaming_connection_leases", "connected_at")
    op.drop_column("gaming_connection_leases", "connection_token_expires_at")
    op.drop_column("gaming_connection_leases", "connection_token_hash")
