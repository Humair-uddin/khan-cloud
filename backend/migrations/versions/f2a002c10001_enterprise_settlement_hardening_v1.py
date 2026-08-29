"""enterprise settlement hardening v1

Revision ID: f2a002c10001
Revises: f2a002b10002
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f2a002c10001"
down_revision = "f2a002b10002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_financial_obligations",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "wallet_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "chargeback_dispute_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "receivable_account_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(length=60),
            nullable=False,
        ),
        sa.Column(
            "provider_reference",
            sa.String(length=180),
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
        ),
        sa.Column(
            "original_amount_minor",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "outstanding_amount_minor",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
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

        sa.CheckConstraint(
            "original_amount_minor > 0",
            name=(
                "ck_customer_obligation_"
                "original_positive"
            ),
        ),
        sa.CheckConstraint(
            "outstanding_amount_minor >= 0",
            name=(
                "ck_customer_obligation_"
                "outstanding_nonnegative"
            ),
        ),
        sa.CheckConstraint(
            "outstanding_amount_minor "
            "<= original_amount_minor",
            name=(
                "ck_customer_obligation_"
                "outstanding_lte_original"
            ),
        ),

        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["customer_wallets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["chargeback_dispute_id"],
            ["chargeback_disputes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["receivable_account_id"],
            ["financial_accounts.id"],
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "chargeback_dispute_id",
        ),

        sa.UniqueConstraint(
            "provider",
            "provider_reference",
            name=(
                "uq_customer_obligation_"
                "provider_reference"
            ),
        ),
    )

    op.create_index(
        op.f(
            "ix_customer_financial_obligations_"
            "organization_id"
        ),
        "customer_financial_obligations",
        ["organization_id"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_customer_financial_obligations_"
            "user_id"
        ),
        "customer_financial_obligations",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_customer_financial_obligations_"
            "wallet_id"
        ),
        "customer_financial_obligations",
        ["wallet_id"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_customer_financial_obligations_"
            "status"
        ),
        "customer_financial_obligations",
        ["status"],
        unique=False,
    )

    op.create_check_constraint(
        "ck_payment_provider_reference_type_nonempty",
        "payment_provider_references",
        "length(btrim(reference_type)) > 0",
    )

    op.create_check_constraint(
        "ck_payment_provider_reference_value_nonempty",
        "payment_provider_references",
        "length(btrim(provider_reference)) > 0",
    )

    op.create_check_constraint(
        "ck_payment_provider_internal_type_nonempty",
        "payment_provider_references",
        "length(btrim(internal_resource_type)) > 0",
    )


def downgrade():
    op.drop_constraint(
        "ck_payment_provider_internal_type_nonempty",
        "payment_provider_references",
        type_="check",
    )

    op.drop_constraint(
        "ck_payment_provider_reference_value_nonempty",
        "payment_provider_references",
        type_="check",
    )

    op.drop_constraint(
        "ck_payment_provider_reference_type_nonempty",
        "payment_provider_references",
        type_="check",
    )

    op.drop_index(
        op.f(
            "ix_customer_financial_obligations_"
            "status"
        ),
        table_name="customer_financial_obligations",
    )

    op.drop_index(
        op.f(
            "ix_customer_financial_obligations_"
            "wallet_id"
        ),
        table_name="customer_financial_obligations",
    )

    op.drop_index(
        op.f(
            "ix_customer_financial_obligations_"
            "user_id"
        ),
        table_name="customer_financial_obligations",
    )

    op.drop_index(
        op.f(
            "ix_customer_financial_obligations_"
            "organization_id"
        ),
        table_name="customer_financial_obligations",
    )

    op.drop_table(
        "customer_financial_obligations"
    )
