"""gaming session lifecycle v1
Revision ID: 16d99df1a001
Revises: b41c9d2e7f60, d94a7f8b9c83
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "16d99df1a001"
down_revision = ("b41c9d2e7f60", "d94a7f8b9c83")
branch_labels = None
depends_on = None


def _basecols():
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade():
    op.create_table("gaming_sessions",
        sa.Column("organization_id", sa.UUID(), nullable=False), sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=True), sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="pending"), sa.Column("desired_state", sa.String(40), nullable=False, server_default="running"),
        sa.Column("minimum_vram_mb", sa.Integer(), nullable=False, server_default="8192"), sa.Column("requested_cpu", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("requested_memory_bytes", sa.BigInteger(), nullable=False, server_default="0"), sa.Column("requested_storage_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("gpu_uuid", sa.String(160), nullable=False, server_default=""), sa.Column("gpu_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("gpu_vram_mb", sa.Integer(), nullable=False, server_default="0"), sa.Column("streaming_backend", sa.String(50), nullable=False, server_default="sunshine"),
        sa.Column("runtime_id", sa.String(255), nullable=False, server_default=""), sa.Column("connection_info", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True), sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_category", sa.String(80), nullable=False, server_default=""), sa.Column("failure_message", sa.String(500), nullable=False, server_default=""),
        *_basecols(), sa.ForeignKeyConstraint(["organization_id"],["organizations.id"],ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"],["users.id"],ondelete="RESTRICT"), sa.ForeignKeyConstraint(["node_id"],["nodes.id"],ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))
    for col in ("organization_id","created_by_user_id","node_id","name","status"):
        op.create_index(f"ix_gaming_sessions_{col}", "gaming_sessions", [col])
    op.create_table("gaming_reservations",
        sa.Column("gaming_session_id",sa.UUID(),nullable=False),sa.Column("node_id",sa.UUID(),nullable=False),sa.Column("gpu_uuid",sa.String(160),nullable=False),
        sa.Column("cpu",sa.Integer(),nullable=False),sa.Column("memory_bytes",sa.BigInteger(),nullable=False),sa.Column("storage_bytes",sa.BigInteger(),nullable=False),
        sa.Column("status",sa.String(30),nullable=False,server_default="reserved"),sa.Column("released_at",sa.DateTime(timezone=True),nullable=True),*_basecols(),
        sa.ForeignKeyConstraint(["gaming_session_id"],["gaming_sessions.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["node_id"],["nodes.id"],ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("gaming_session_id",name="uq_gaming_reservation_session"))
    for col in ("gaming_session_id","node_id","gpu_uuid","status"):
        op.create_index(f"ix_gaming_reservations_{col}", "gaming_reservations", [col])
    op.add_column("node_jobs", sa.Column("gaming_session_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_node_jobs_gaming_session", "node_jobs", "gaming_sessions", ["gaming_session_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_node_jobs_gaming_session_id", "node_jobs", ["gaming_session_id"])


def downgrade():
    op.drop_index("ix_node_jobs_gaming_session_id", table_name="node_jobs"); op.drop_constraint("fk_node_jobs_gaming_session", "node_jobs", type_="foreignkey"); op.drop_column("node_jobs", "gaming_session_id")
    op.drop_table("gaming_reservations"); op.drop_table("gaming_sessions")
