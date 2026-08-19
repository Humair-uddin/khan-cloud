"""gaming host availability readiness v1

Revision ID: 83a4f2d91c60
Revises: 6e2f9a4c1d70
"""

from alembic import op
import sqlalchemy as sa


revision = "83a4f2d91c60"
down_revision = "6e2f9a4c1d70"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "nodes",
        sa.Column(
            "gaming_accepting_work",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_index(
        "ix_nodes_gaming_accepting_work",
        "nodes",
        ["gaming_accepting_work"],
    )


def downgrade():
    op.drop_index(
        "ix_nodes_gaming_accepting_work",
        table_name="nodes",
    )
    op.drop_column(
        "nodes",
        "gaming_accepting_work",
    )
