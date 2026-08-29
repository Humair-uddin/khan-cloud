"""payout execution and obligation recovery v1

Revision ID: f2a002e10001
Revises: f2a002d10002
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a002e10001"
down_revision = "f2a002d10002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chargeback_disputes",
        sa.Column(
            "resolution_reference",
            sa.String(length=180),
            nullable=False,
            server_default="",
        ),
    )

    op.add_column(
        "chargeback_disputes",
        sa.Column(
            "resolution_reason",
            sa.String(length=500),
            nullable=False,
            server_default="",
        ),
    )

    op.create_table(
        "customer_obligation_payments",
        sa.Column(
            "obligation_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "wallet_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "amount_minor",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
        ),
        sa.Column(
            "payment_type",
            sa.String(length=30),
            nullable=False,
            server_default="collection",
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "ledger_transaction_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "external_reference",
            sa.String(length=180),
            nullable=False,
            server_default="",
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
            "amount_minor > 0",
            name=(
                "ck_customer_obligation_"
                "payment_positive"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["obligation_id"],
            ["customer_financial_obligations.id"],
            ondelete="RESTRICT",
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
            "idempotency_key",
            name=(
                "uq_customer_obligation_payment_"
                "idempotency"
            ),
        ),
        sa.UniqueConstraint(
            "ledger_transaction_id",
            name=(
                "uq_customer_obligation_payment_"
                "ledger_transaction"
            ),
        ),
    )

    op.create_index(
        "ix_customer_obligation_payments_obligation_id",
        "customer_obligation_payments",
        ["obligation_id"],
    )

    op.create_index(
        "ix_customer_obligation_payments_organization_id",
        "customer_obligation_payments",
        ["organization_id"],
    )

    op.create_index(
        "ix_customer_obligation_payments_wallet_id",
        "customer_obligation_payments",
        ["wallet_id"],
    )

    op.create_index(
        "ix_customer_obligation_payments_idempotency_key",
        "customer_obligation_payments",
        ["idempotency_key"],
        unique=True,
    )

    #
    # Extend existing outbox status contract.
    #
    op.drop_constraint(
        "ck_payment_outbox_status",
        "payment_financial_outbox",
        type_="check",
    )

    op.create_check_constraint(
        "ck_payment_outbox_status",
        "payment_financial_outbox",
        (
            "status IN "
            "('pending','processing','processed',"
            "'failed','dead_letter')"
        ),
    )

    op.create_check_constraint(
        "ck_customer_obligation_status",
        "customer_financial_obligations",
        (
            "status IN "
            "('outstanding','partially_paid','paid')"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_customer_obligation_status",
        "customer_financial_obligations",
        type_="check",
    )

    op.drop_constraint(
        "ck_payment_outbox_status",
        "payment_financial_outbox",
        type_="check",
    )

    op.create_check_constraint(
        "ck_payment_outbox_status",
        "payment_financial_outbox",
        (
            "status IN "
            "('pending','processing','processed','failed')"
        ),
    )

    op.drop_index(
        "ix_customer_obligation_payments_idempotency_key",
        table_name="customer_obligation_payments",
    )

    op.drop_index(
        "ix_customer_obligation_payments_wallet_id",
        table_name="customer_obligation_payments",
    )

    op.drop_index(
        "ix_customer_obligation_payments_organization_id",
        table_name="customer_obligation_payments",
    )

    op.drop_index(
        "ix_customer_obligation_payments_obligation_id",
        table_name="customer_obligation_payments",
    )

    op.drop_table(
        "customer_obligation_payments"
    )

    op.drop_column(
        "chargeback_disputes",
        "resolution_reason",
    )

    op.drop_column(
        "chargeback_disputes",
        "resolution_reference",
    )
