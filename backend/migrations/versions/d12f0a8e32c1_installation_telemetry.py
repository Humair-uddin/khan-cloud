"""installation telemetry

Revision ID: d12f0a8e32c1
Revises: b8f11a29e6d1
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d12f0a8e32c1"
down_revision: Union[str, Sequence[str], None] = "b8f11a29e6d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("installation_status", sa.String(length=40), nullable=False, server_default="not_started"))
    op.add_column("nodes", sa.Column("installation_stage", sa.String(length=60), nullable=False, server_default=""))
    op.add_column("nodes", sa.Column("installation_failure_category", sa.String(length=60), nullable=False, server_default=""))
    op.add_column("nodes", sa.Column("installation_message", sa.String(length=500), nullable=False, server_default=""))
    op.add_column("nodes", sa.Column("installation_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_nodes_installation_status", "nodes", ["installation_status"])
    op.create_index("ix_nodes_installation_failure_category", "nodes", ["installation_failure_category"])
    op.create_index("ix_nodes_installation_updated_at", "nodes", ["installation_updated_at"])

    op.create_table(
        "installation_events",
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("deployment_profile_id", sa.UUID(), nullable=True),
        sa.Column("transaction_id", sa.String(length=64), nullable=False),
        sa.Column("feature_pack_id", sa.String(length=150), nullable=False),
        sa.Column("feature_pack_version", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=60), nullable=False),
        sa.Column("failure_category", sa.String(length=60), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_installation_events_node_id", "installation_events", ["node_id"])
    op.create_index("ix_installation_events_deployment_profile_id", "installation_events", ["deployment_profile_id"])
    op.create_index("ix_installation_events_transaction_id", "installation_events", ["transaction_id"])
    op.create_index("ix_installation_events_status", "installation_events", ["status"])
    op.create_index("ix_installation_events_stage", "installation_events", ["stage"])
    op.create_index("ix_installation_events_failure_category", "installation_events", ["failure_category"])


def downgrade() -> None:
    op.drop_table("installation_events")
    op.drop_index("ix_nodes_installation_updated_at", table_name="nodes")
    op.drop_index("ix_nodes_installation_failure_category", table_name="nodes")
    op.drop_index("ix_nodes_installation_status", table_name="nodes")
    op.drop_column("nodes", "installation_updated_at")
    op.drop_column("nodes", "installation_message")
    op.drop_column("nodes", "installation_failure_category")
    op.drop_column("nodes", "installation_stage")
    op.drop_column("nodes", "installation_status")
