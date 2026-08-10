"""add gateway reconciliation retry metadata

Revision ID: a27d5c9e41f0
Revises: f19c4e7a2b31
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "a27d5c9e41f0"
down_revision = "f19c4e7a2b31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "port_mappings",
        sa.Column(
            "reconcile_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "port_mappings",
        sa.Column(
            "reconcile_last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "port_mappings",
        sa.Column(
            "reconcile_next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_port_mappings_reconcile_next_attempt_at",
        "port_mappings",
        ["reconcile_next_attempt_at"],
        unique=False,
    )

    op.alter_column(
        "port_mappings",
        "reconcile_attempt_count",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_port_mappings_reconcile_next_attempt_at",
        table_name="port_mappings",
    )

    op.drop_column(
        "port_mappings",
        "reconcile_next_attempt_at",
    )

    op.drop_column(
        "port_mappings",
        "reconcile_last_attempt_at",
    )

    op.drop_column(
        "port_mappings",
        "reconcile_attempt_count",
    )
