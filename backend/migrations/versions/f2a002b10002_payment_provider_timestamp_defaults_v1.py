"""payment provider timestamp defaults v1

Revision ID: f2a002b10002
Revises: f2a002b10001
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a002b10002"
down_revision = "f2a002b10001"
branch_labels = None
depends_on = None


TABLES = (
    "payment_providers",
    "payment_provider_references",
    "payment_webhook_receipts",
)


def upgrade():
    for table in TABLES:
        op.alter_column(
            table,
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.text("now()"),
        )

        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.text("now()"),
        )


def downgrade():
    for table in reversed(TABLES):
        op.alter_column(
            table,
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )

        op.alter_column(
            table,
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=None,
        )
