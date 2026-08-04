"""add nodes

Revision ID: cc41a40d7f22
Revises: 9f4ad9a31a70
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "cc41a40d7f22"
down_revision: Union[str, Sequence[str], None] = "9f4ad9a31a70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("machine_id", sa.String(length=255), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("operating_system", sa.String(length=255), nullable=False),
        sa.Column("kernel_version", sa.String(length=255), nullable=False),
        sa.Column("agent_version", sa.String(length=50), nullable=False),
        sa.Column("cpu_model", sa.String(length=255), nullable=False),
        sa.Column("cpu_logical_count", sa.Integer(), nullable=False),
        sa.Column("memory_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("docker_available", sa.Boolean(), nullable=False),
        sa.Column("nvidia_available", sa.Boolean(), nullable=False),
        sa.Column("gpu_count", sa.Integer(), nullable=False),
        sa.Column("management_ip", sa.String(length=64), nullable=False),
        sa.Column("production_ip", sa.String(length=64), nullable=False),
        sa.Column("inventory", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_nodes_machine_id", "nodes", ["machine_id"], unique=True)
    op.create_index("ix_nodes_name", "nodes", ["name"], unique=True)
    op.create_index("ix_nodes_status", "nodes", ["status"], unique=False)
    op.create_index("ix_nodes_last_seen_at", "nodes", ["last_seen_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_nodes_last_seen_at", table_name="nodes")
    op.drop_index("ix_nodes_status", table_name="nodes")
    op.drop_index("ix_nodes_name", table_name="nodes")
    op.drop_index("ix_nodes_machine_id", table_name="nodes")
    op.drop_table("nodes")
