"""add gateway ingress topology

Revision ID: f19c4e7a2b31
Revises: e84b7c1d2a90
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "f19c4e7a2b31"
down_revision = "e84b7c1d2a90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "public_gateways",
        sa.Column(
            "ingress_mode",
            sa.String(length=30),
            nullable=False,
            server_default="direct",
        ),
    )

    op.add_column(
        "public_gateways",
        sa.Column(
            "wan_interface",
            sa.String(length=80),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_public_gateway_ingress_mode",
        "public_gateways",
        "ingress_mode IN ('direct', 'upstream_nat')",
    )

    op.alter_column(
        "public_gateways",
        "ingress_mode",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_public_gateway_ingress_mode",
        "public_gateways",
        type_="check",
    )

    op.drop_column(
        "public_gateways",
        "wan_interface",
    )

    op.drop_column(
        "public_gateways",
        "ingress_mode",
    )
