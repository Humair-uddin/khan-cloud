"""port mapping reconciliation state

Revision ID: e84b7c1d2a90
Revises: c75f8d75b793
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e84b7c1d2a90"
down_revision: str | None = "c75f8d75b793"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "port_mappings",
        sa.Column(
            "reconcile_action",
            sa.String(length=20),
            nullable=False,
            server_default="apply",
        ),
    )
    op.add_column(
        "port_mappings",
        sa.Column(
            "reconcile_error",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "port_mappings",
        sa.Column(
            "reconciled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "port_mappings",
        sa.Column(
            "external_id",
            sa.String(length=120),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_port_mapping_reconcile_action",
        "port_mappings",
        "reconcile_action IN ('apply', 'remove')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_port_mapping_reconcile_action",
        "port_mappings",
        type_="check",
    )
    op.drop_column("port_mappings", "external_id")
    op.drop_column("port_mappings", "reconciled_at")
    op.drop_column("port_mappings", "reconcile_error")
    op.drop_column("port_mappings", "reconcile_action")
