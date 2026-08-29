"""financial lifecycle v1

Revision ID: f1a001b10002
Revises: f1a001b10001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f1a001b10002"
down_revision = "f1a001b10001"
branch_labels = None
depends_on = None


def _base_columns():
    return (
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
    )


def upgrade():
    op.create_table(
        "finance_refunds",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("wallet_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "external_reference",
            sa.String(180),
            nullable=False,
            server_default="",
        ),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("ledger_transaction_id", sa.UUID(), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "amount_minor > 0",
            name="ck_finance_refund_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["customer_wallets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("ledger_transaction_id"),
    )

    for col in (
        "organization_id",
        "wallet_id",
        "status",
        "external_reference",
        "idempotency_key",
    ):
        op.create_index(
            f"ix_finance_refunds_{col}",
            "finance_refunds",
            [col],
        )

    op.create_table(
        "chargeback_disputes",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("wallet_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("provider_dispute_id", sa.String(180), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="posted",
        ),
        sa.Column(
            "reason",
            sa.String(500),
            nullable=False,
            server_default="",
        ),
        sa.Column("ledger_transaction_id", sa.UUID(), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "amount_minor > 0",
            name="ck_chargeback_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["customer_wallets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_dispute_id",
            name="uq_chargeback_provider_dispute",
        ),
        sa.UniqueConstraint("ledger_transaction_id"),
    )

    for col in (
        "organization_id",
        "wallet_id",
        "provider",
        "status",
    ):
        op.create_index(
            f"ix_chargeback_disputes_{col}",
            "chargeback_disputes",
            [col],
        )

    op.create_table(
        "financial_adjustments",
        sa.Column("adjustment_type", sa.String(50), nullable=False),
        sa.Column("debit_account_id", sa.UUID(), nullable=False),
        sa.Column("credit_account_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("ledger_transaction_id", sa.UUID(), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "amount_minor > 0",
            name="ck_financial_adjustment_amount_positive",
        ),
        sa.CheckConstraint(
            "debit_account_id <> credit_account_id",
            name="ck_financial_adjustment_accounts_different",
        ),
        sa.ForeignKeyConstraint(
            ["debit_account_id"],
            ["financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["credit_account_id"],
            ["financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("ledger_transaction_id"),
    )

    op.create_index(
        "ix_financial_adjustments_adjustment_type",
        "financial_adjustments",
        ["adjustment_type"],
    )
    op.create_index(
        "ix_financial_adjustments_actor_user_id",
        "financial_adjustments",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_financial_adjustments_idempotency_key",
        "financial_adjustments",
        ["idempotency_key"],
    )

    op.create_table(
        "treasury_settlement_batches",
        sa.Column("settlement_type", sa.String(50), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="posted",
        ),
        sa.Column(
            "external_reference",
            sa.String(180),
            nullable=False,
            server_default="",
        ),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("ledger_transaction_id", sa.UUID(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_base_columns(),
        sa.CheckConstraint(
            "amount_minor > 0",
            name="ck_treasury_settlement_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("ledger_transaction_id"),
    )

    for col in (
        "settlement_type",
        "provider",
        "currency",
        "status",
        "external_reference",
        "idempotency_key",
    ):
        op.create_index(
            f"ix_treasury_settlement_batches_{col}",
            "treasury_settlement_batches",
            [col],
        )

    for table, columns in {
        "finance_refunds": (
            "status",
            "external_reference",
        ),
        "chargeback_disputes": (
            "status",
            "reason",
        ),
        "treasury_settlement_batches": (
            "status",
            "external_reference",
            "metadata_json",
        ),
    }.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                server_default=None,
            )


def downgrade():
    for table in (
        "treasury_settlement_batches",
        "financial_adjustments",
        "chargeback_disputes",
        "finance_refunds",
    ):
        op.drop_table(table)
