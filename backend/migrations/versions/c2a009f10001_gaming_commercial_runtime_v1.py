"""gaming commercial runtime v1

Revision ID: c2a009f10001
Revises: f2a002f10001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c2a009f10001"
down_revision = "f2a002f10001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gaming_sessions", sa.Column("product_sku_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("gaming_sessions", sa.Column("usage_reservation_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("gaming_sessions", sa.Column("play_request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("gaming_sessions", sa.Column("billing_currency", sa.String(length=3), server_default="", nullable=False))
    op.add_column("gaming_sessions", sa.Column("per_minute_price_minor", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("gaming_sessions", sa.Column("host_payout_per_minute_minor", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("gaming_sessions", sa.Column("admission_reserved_minor", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("gaming_sessions", sa.Column("pricing_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("gaming_sessions", sa.Column("last_metered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_sessions", sa.Column("billing_finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gaming_sessions", sa.Column("billing_stop_reason", sa.String(length=80), server_default="", nullable=False))

    op.create_foreign_key("fk_gaming_sessions_product_sku", "gaming_sessions", "product_skus", ["product_sku_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_gaming_sessions_usage_reservation", "gaming_sessions", "usage_reservations", ["usage_reservation_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_gaming_sessions_product_sku_id", "gaming_sessions", ["product_sku_id"], unique=False)
    op.create_index("ix_gaming_sessions_usage_reservation_id", "gaming_sessions", ["usage_reservation_id"], unique=False)
    op.create_index("ux_gaming_sessions_play_request_id", "gaming_sessions", ["play_request_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_gaming_sessions_play_request_id", table_name="gaming_sessions")
    op.drop_index("ix_gaming_sessions_usage_reservation_id", table_name="gaming_sessions")
    op.drop_index("ix_gaming_sessions_product_sku_id", table_name="gaming_sessions")
    op.drop_constraint("fk_gaming_sessions_usage_reservation", "gaming_sessions", type_="foreignkey")
    op.drop_constraint("fk_gaming_sessions_product_sku", "gaming_sessions", type_="foreignkey")
    for column in (
        "billing_stop_reason",
        "billing_finalized_at",
        "last_metered_at",
        "pricing_snapshot",
        "admission_reserved_minor",
        "host_payout_per_minute_minor",
        "per_minute_price_minor",
        "billing_currency",
        "play_request_id",
        "usage_reservation_id",
        "product_sku_id",
    ):
        op.drop_column("gaming_sessions", column)
