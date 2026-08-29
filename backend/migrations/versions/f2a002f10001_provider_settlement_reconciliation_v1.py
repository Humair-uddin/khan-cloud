"""provider settlement reconciliation v1

Revision ID: f2a002f10001
Revises: f2a002e10001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f2a002f10001"
down_revision = "f2a002e10001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "reconciliation_type",
            sa.String(length=40),
            nullable=False,
            server_default="provider_event",
        ),
    )

    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "outcome",
            sa.String(length=30),
            nullable=False,
            server_default="pending_review",
        ),
    )

    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "provider_amount_minor",
            sa.BigInteger(),
            nullable=True,
        ),
    )

    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "internal_amount_minor",
            sa.BigInteger(),
            nullable=True,
        ),
    )

    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "provider_currency",
            sa.String(length=3),
            nullable=False,
            server_default="",
        ),
    )

    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "internal_currency",
            sa.String(length=3),
            nullable=False,
            server_default="",
        ),
    )

    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "internal_resource_type",
            sa.String(length=50),
            nullable=False,
            server_default="",
        ),
    )

    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "internal_resource_id",
            sa.UUID(),
            nullable=True,
        ),
    )

    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "resolution_reason",
            sa.String(length=500),
            nullable=False,
            server_default="",
        ),
    )

    op.add_column(
        "payment_reconciliation_events",
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_check_constraint(
        "ck_payment_reconciliation_outcome",
        "payment_reconciliation_events",
        (
            "outcome IN "
            "('matched','amount_mismatch','currency_mismatch',"
            "'missing_internal','missing_provider',"
            "'duplicate_provider','pending_review','resolved')"
        ),
    )

    op.create_index(
        "ix_payment_reconciliation_events_outcome",
        "payment_reconciliation_events",
        ["outcome"],
    )

    op.create_table(
        "payment_provider_settlement_batches",
        sa.Column(
            "provider_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "provider_code",
            sa.String(length=60),
            nullable=False,
        ),
        sa.Column(
            "provider_settlement_reference",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "settlement_currency",
            sa.String(length=3),
            nullable=False,
        ),
        sa.Column(
            "gross_amount_minor",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "fee_amount_minor",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "net_amount_minor",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "settlement_date",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="received",
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "credential_reference_snapshot",
            sa.String(length=240),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "gross_amount_minor >= 0",
            name="ck_payment_provider_settlement_gross",
        ),
        sa.CheckConstraint(
            "fee_amount_minor >= 0",
            name="ck_payment_provider_settlement_fee",
        ),
        sa.CheckConstraint(
            "net_amount_minor = "
            "gross_amount_minor - fee_amount_minor",
            name="ck_payment_provider_settlement_net",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_payment_provider_settlement_hash",
        ),
        sa.CheckConstraint(
            "status IN "
            "('received','reconciling','reconciled',"
            "'pending_review','failed')",
            name="ck_payment_provider_settlement_status",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["payment_providers.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_id",
            "provider_settlement_reference",
            name="uq_payment_provider_settlement_reference",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_payment_provider_settlement_idempotency",
        ),
    )

    op.create_index(
        "ix_payment_provider_settlement_batches_provider_id",
        "payment_provider_settlement_batches",
        ["provider_id"],
    )

    op.create_index(
        "ix_payment_provider_settlement_batches_provider_code",
        "payment_provider_settlement_batches",
        ["provider_code"],
    )

    op.create_index(
        "ix_payment_provider_settlement_batches_settlement_currency",
        "payment_provider_settlement_batches",
        ["settlement_currency"],
    )

    op.create_index(
        "ix_payment_provider_settlement_batches_status",
        "payment_provider_settlement_batches",
        ["status"],
    )

    op.create_index(
        "ix_payment_provider_settlement_batches_idempotency_key",
        "payment_provider_settlement_batches",
        ["idempotency_key"],
        unique=True,
    )

    op.create_table(
        "payment_provider_settlement_items",
        sa.Column(
            "settlement_batch_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "provider_line_id",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "provider_transaction_reference",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "presentment_currency",
            sa.String(length=3),
            nullable=False,
        ),
        sa.Column(
            "settlement_currency",
            sa.String(length=3),
            nullable=False,
        ),
        sa.Column(
            "gross_amount_minor",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "fee_amount_minor",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "net_amount_minor",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "explicit_fx_transaction_id",
            sa.UUID(),
            nullable=True,
        ),
        sa.Column(
            "content_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "reconciliation_status",
            sa.String(length=30),
            nullable=False,
            server_default="pending_review",
        ),
        sa.Column(
            "reconciliation_event_id",
            sa.UUID(),
            nullable=True,
        ),
        sa.Column(
            "internal_resource_type",
            sa.String(length=50),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "internal_resource_id",
            sa.UUID(),
            nullable=True,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "gross_amount_minor >= 0",
            name="ck_payment_provider_settlement_item_gross",
        ),
        sa.CheckConstraint(
            "fee_amount_minor >= 0",
            name="ck_payment_provider_settlement_item_fee",
        ),
        sa.CheckConstraint(
            "net_amount_minor = "
            "gross_amount_minor - fee_amount_minor",
            name="ck_payment_provider_settlement_item_net",
        ),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_payment_provider_settlement_item_hash",
        ),
        sa.CheckConstraint(
            "reconciliation_status IN "
            "('matched','amount_mismatch','currency_mismatch',"
            "'missing_internal','missing_provider',"
            "'duplicate_provider','pending_review','resolved')",
            name=(
                "ck_payment_provider_settlement_"
                "item_reconciliation"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["settlement_batch_id"],
            ["payment_provider_settlement_batches.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reconciliation_event_id"],
            ["payment_reconciliation_events.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "settlement_batch_id",
            "provider_line_id",
            name="uq_payment_provider_settlement_line",
        ),
    )

    op.create_index(
        "ix_payment_provider_settlement_items_settlement_batch_id",
        "payment_provider_settlement_items",
        ["settlement_batch_id"],
    )

    op.create_index(
        "ix_pp_settle_item_txn_ref",
        "payment_provider_settlement_items",
        ["provider_transaction_reference"],
    )

    op.create_index(
        "ix_payment_provider_settlement_items_event_type",
        "payment_provider_settlement_items",
        ["event_type"],
    )

    op.create_index(
        "ix_payment_provider_settlement_items_reconciliation_status",
        "payment_provider_settlement_items",
        ["reconciliation_status"],
    )

    op.create_index(
        "ix_payment_provider_settlement_item_reference",
        "payment_provider_settlement_items",
        [
            "settlement_batch_id",
            "provider_transaction_reference",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_provider_settlement_item_reference",
        table_name="payment_provider_settlement_items",
    )

    op.drop_index(
        "ix_payment_provider_settlement_items_reconciliation_status",
        table_name="payment_provider_settlement_items",
    )

    op.drop_index(
        "ix_payment_provider_settlement_items_event_type",
        table_name="payment_provider_settlement_items",
    )

    op.drop_index(
        "ix_pp_settle_item_txn_ref",
        table_name="payment_provider_settlement_items",
    )

    op.drop_index(
        "ix_payment_provider_settlement_items_settlement_batch_id",
        table_name="payment_provider_settlement_items",
    )

    op.drop_table(
        "payment_provider_settlement_items"
    )

    op.drop_index(
        "ix_payment_provider_settlement_batches_idempotency_key",
        table_name="payment_provider_settlement_batches",
    )

    op.drop_index(
        "ix_payment_provider_settlement_batches_status",
        table_name="payment_provider_settlement_batches",
    )

    op.drop_index(
        "ix_payment_provider_settlement_batches_settlement_currency",
        table_name="payment_provider_settlement_batches",
    )

    op.drop_index(
        "ix_payment_provider_settlement_batches_provider_code",
        table_name="payment_provider_settlement_batches",
    )

    op.drop_index(
        "ix_payment_provider_settlement_batches_provider_id",
        table_name="payment_provider_settlement_batches",
    )

    op.drop_table(
        "payment_provider_settlement_batches"
    )

    op.drop_index(
        "ix_payment_reconciliation_events_outcome",
        table_name="payment_reconciliation_events",
    )

    op.drop_constraint(
        "ck_payment_reconciliation_outcome",
        "payment_reconciliation_events",
        type_="check",
    )

    op.drop_column(
        "payment_reconciliation_events",
        "resolved_at",
    )
    op.drop_column(
        "payment_reconciliation_events",
        "resolution_reason",
    )
    op.drop_column(
        "payment_reconciliation_events",
        "internal_resource_id",
    )
    op.drop_column(
        "payment_reconciliation_events",
        "internal_resource_type",
    )
    op.drop_column(
        "payment_reconciliation_events",
        "internal_currency",
    )
    op.drop_column(
        "payment_reconciliation_events",
        "provider_currency",
    )
    op.drop_column(
        "payment_reconciliation_events",
        "internal_amount_minor",
    )
    op.drop_column(
        "payment_reconciliation_events",
        "provider_amount_minor",
    )
    op.drop_column(
        "payment_reconciliation_events",
        "outcome",
    )
    op.drop_column(
        "payment_reconciliation_events",
        "reconciliation_type",
    )
