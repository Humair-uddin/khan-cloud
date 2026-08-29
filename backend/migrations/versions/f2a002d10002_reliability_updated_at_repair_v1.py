"""repair inherited updated_at columns on payment reliability tables

Revision ID: f2a002d10002
Revises: f2a002d10001
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a002d10002"
down_revision = "f2a002d10001"
branch_labels = None
depends_on = None


_TABLES = (
    "payment_webhook_forensic_events",
    "payment_provider_health_events",
    "payment_financial_outbox",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in _TABLES:
        columns = {
            column["name"]
            for column in inspector.get_columns(table)
        }

        if "updated_at" not in columns:
            op.add_column(
                table,
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.text("now()"),
                    nullable=False,
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in reversed(_TABLES):
        columns = {
            column["name"]
            for column in inspector.get_columns(table)
        }

        if "updated_at" in columns:
            op.drop_column(
                table,
                "updated_at",
            )
