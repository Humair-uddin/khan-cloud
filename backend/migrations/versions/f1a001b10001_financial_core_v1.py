"""financial core v1

Revision ID: f1a001b10001
Revises: b7d5c1a92f40
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f1a001b10001"
down_revision = "b7d5c1a92f40"
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
    # Security migration for the legacy Billing V2 token table.
    #
    # KF-001B2 proved this table currently contains zero rows.
    # Refuse migration if plaintext token data unexpectedly appears
    # between validation and deployment rather than mislabelling
    # plaintext as encrypted data.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM payment_method_tokens
                LIMIT 1
            ) THEN
                RAISE EXCEPTION
                    'KF-001 refuses plaintext payment token migration';
            END IF;
        END
        $$;
        """
    )

    op.alter_column(
        "payment_method_tokens",
        "provider_token",
        new_column_name="encrypted_provider_token",
        existing_type=sa.String(255),
        type_=sa.String(4096),
        existing_nullable=False,
    )
    op.add_column(
        "payment_method_tokens",
        sa.Column(
            "encryption_key_version",
            sa.String(40),
            nullable=False,
            server_default="unconfigured",
        ),
    )
    op.add_column(
        "payment_method_tokens",
        sa.Column(
            "token_fingerprint",
            sa.String(128),
            nullable=False,
            server_default="",
        ),
    )
    op.create_index(
        "ix_payment_method_tokens_token_fingerprint",
        "payment_method_tokens",
        ["token_fingerprint"],
    )
    op.alter_column(
        "payment_method_tokens",
        "encryption_key_version",
        server_default=None,
    )
    op.alter_column(
        "payment_method_tokens",
        "token_fingerprint",
        server_default=None,
    )

    op.create_table(
        "financial_accounts",
        sa.Column("account_code", sa.String(180), nullable=False),
        sa.Column("account_type", sa.String(60), nullable=False),
        sa.Column("normal_side", sa.String(6), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("host_node_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_base_columns(),
        sa.CheckConstraint(
            "normal_side IN ('debit','credit')",
            name="ck_financial_accounts_normal_side",
        ),
        sa.CheckConstraint(
            "currency IN ('PKR','USD')",
            name="ck_financial_accounts_currency",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["host_node_id"],
            ["nodes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_code"),
    )

    for col in (
        "account_code",
        "account_type",
        "currency",
        "organization_id",
        "user_id",
        "host_node_id",
        "status",
    ):
        op.create_index(
            f"ix_financial_accounts_{col}",
            "financial_accounts",
            [col],
        )

    op.create_table(
        "ledger_transactions",
        sa.Column("transaction_type", sa.String(60), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="posted",
        ),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "external_reference",
            sa.String(255),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "description",
            sa.String(500),
            nullable=False,
            server_default="",
        ),
        sa.Column("reversed_transaction_id", sa.UUID(), nullable=True),
        sa.Column(
            "posted_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_base_columns(),
        sa.CheckConstraint(
            "currency IN ('PKR','USD')",
            name="ck_ledger_transactions_currency",
        ),
        sa.CheckConstraint(
            "status IN ('posted','reversed')",
            name="ck_ledger_transactions_status",
        ),
        sa.ForeignKeyConstraint(
            ["reversed_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )

    for col in (
        "transaction_type",
        "currency",
        "status",
        "idempotency_key",
        "external_reference",
        "reversed_transaction_id",
    ):
        op.create_index(
            f"ix_ledger_transactions_{col}",
            "ledger_transactions",
            [col],
        )

    op.create_table(
        "ledger_entries",
        sa.Column("transaction_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("side", sa.String(6), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "memo",
            sa.String(255),
            nullable=False,
            server_default="",
        ),
        *_base_columns(),
        sa.CheckConstraint(
            "side IN ('debit','credit')",
            name="ck_ledger_entries_side",
        ),
        sa.CheckConstraint(
            "amount_minor > 0",
            name="ck_ledger_entries_positive_amount",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ledger_entries_transaction_id",
        "ledger_entries",
        ["transaction_id"],
    )
    op.create_index(
        "ix_ledger_entries_account_id",
        "ledger_entries",
        ["account_id"],
    )

    op.create_table(
        "customer_wallets",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("available_account_id", sa.UUID(), nullable=False),
        sa.Column("reserved_account_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="active",
        ),
        *_base_columns(),
        sa.CheckConstraint(
            "currency IN ('PKR','USD')",
            name="ck_customer_wallet_currency",
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
            ["available_account_id"],
            ["financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reserved_account_id"],
            ["financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "currency",
            name="uq_customer_wallet_org_currency",
        ),
        sa.UniqueConstraint("available_account_id"),
        sa.UniqueConstraint("reserved_account_id"),
    )

    op.create_index(
        "ix_customer_wallets_organization_id",
        "customer_wallets",
        ["organization_id"],
    )
    op.create_index(
        "ix_customer_wallets_user_id",
        "customer_wallets",
        ["user_id"],
    )
    op.create_index(
        "ix_customer_wallets_currency",
        "customer_wallets",
        ["currency"],
    )
    op.create_index(
        "ix_customer_wallets_status",
        "customer_wallets",
        ["status"],
    )

    op.create_table(
        "host_settlement_accounts",
        sa.Column("host_node_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("pending_account_id", sa.UUID(), nullable=False),
        sa.Column("held_account_id", sa.UUID(), nullable=False),
        sa.Column("available_account_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="active",
        ),
        *_base_columns(),
        sa.CheckConstraint(
            "currency IN ('PKR','USD')",
            name="ck_host_settlement_currency",
        ),
        sa.ForeignKeyConstraint(
            ["host_node_id"],
            ["nodes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["pending_account_id"],
            ["financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["held_account_id"],
            ["financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["available_account_id"],
            ["financial_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "host_node_id",
            "currency",
            name="uq_host_settlement_node_currency",
        ),
        sa.UniqueConstraint("pending_account_id"),
        sa.UniqueConstraint("held_account_id"),
        sa.UniqueConstraint("available_account_id"),
    )

    op.create_index(
        "ix_host_settlement_accounts_host_node_id",
        "host_settlement_accounts",
        ["host_node_id"],
    )
    op.create_index(
        "ix_host_settlement_accounts_currency",
        "host_settlement_accounts",
        ["currency"],
    )
    op.create_index(
        "ix_host_settlement_accounts_status",
        "host_settlement_accounts",
        ["status"],
    )

    op.create_table(
        "payment_deposits",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("provider_event_id", sa.String(180), nullable=False),
        sa.Column(
            "provider_reference",
            sa.String(180),
            nullable=False,
            server_default="",
        ),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="confirmed",
        ),
        sa.Column("ledger_transaction_id", sa.UUID(), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "amount_minor > 0",
            name="ck_payment_deposit_amount_positive",
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
            ["ledger_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_payment_deposit_provider_event",
        ),
        sa.UniqueConstraint("ledger_transaction_id"),
    )

    for col in (
        "organization_id",
        "user_id",
        "provider",
        "provider_reference",
        "status",
    ):
        op.create_index(
            f"ix_payment_deposits_{col}",
            "payment_deposits",
            [col],
        )

    op.create_table(
        "usage_reservations",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("wallet_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reserved_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "consumed_minor",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "released_minor",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="reserved",
        ),
        sa.Column(
            "reference_type",
            sa.String(80),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "reference_id",
            sa.String(180),
            nullable=False,
            server_default="",
        ),
        sa.Column("reserve_transaction_id", sa.UUID(), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "reserved_minor > 0",
            name="ck_usage_reservation_positive",
        ),
        sa.CheckConstraint(
            "consumed_minor >= 0",
            name="ck_usage_reservation_consumed_nonnegative",
        ),
        sa.CheckConstraint(
            "released_minor >= 0",
            name="ck_usage_reservation_released_nonnegative",
        ),
        sa.CheckConstraint(
            "consumed_minor + released_minor <= reserved_minor",
            name="ck_usage_reservation_allocation",
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
            ["reserve_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    for col in (
        "organization_id",
        "user_id",
        "wallet_id",
        "status",
        "reference_type",
        "reference_id",
    ):
        op.create_index(
            f"ix_usage_reservations_{col}",
            "usage_reservations",
            [col],
        )

    op.create_table(
        "host_earnings",
        sa.Column("host_node_id", sa.UUID(), nullable=False),
        sa.Column("usage_reservation_id", sa.UUID(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("gross_charge_minor", sa.BigInteger(), nullable=False),
        sa.Column("host_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("platform_revenue_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("earning_transaction_id", sa.UUID(), nullable=False),
        *_base_columns(),
        sa.CheckConstraint(
            "gross_charge_minor > 0",
            name="ck_host_earning_gross_positive",
        ),
        sa.CheckConstraint(
            "host_amount_minor >= 0",
            name="ck_host_earning_host_nonnegative",
        ),
        sa.CheckConstraint(
            "platform_revenue_minor >= 0",
            name="ck_host_earning_revenue_nonnegative",
        ),
        sa.CheckConstraint(
            "host_amount_minor + platform_revenue_minor = gross_charge_minor",
            name="ck_host_earning_split_balanced",
        ),
        sa.ForeignKeyConstraint(
            ["host_node_id"],
            ["nodes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usage_reservation_id"],
            ["usage_reservations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["earning_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("earning_transaction_id"),
    )

    op.create_index(
        "ix_host_earnings_host_node_id",
        "host_earnings",
        ["host_node_id"],
    )
    op.create_index(
        "ix_host_earnings_usage_reservation_id",
        "host_earnings",
        ["usage_reservation_id"],
    )
    op.create_index(
        "ix_host_earnings_status",
        "host_earnings",
        ["status"],
    )

    op.create_table(
        "payout_methods",
        sa.Column("host_node_id", sa.UUID(), nullable=False),
        sa.Column("method_type", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("encrypted_payload", sa.String(4096), nullable=False),
        sa.Column("encryption_key_version", sa.String(40), nullable=False),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column(
            "last4",
            sa.String(4),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "is_preferred",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="active",
        ),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["host_node_id"],
            ["nodes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    for col in (
        "host_node_id",
        "fingerprint",
        "is_preferred",
        "status",
    ):
        op.create_index(
            f"ix_payout_methods_{col}",
            "payout_methods",
            [col],
        )

    # At most one preferred active destination per host.
    op.create_index(
        "uq_payout_methods_one_preferred_host",
        "payout_methods",
        ["host_node_id"],
        unique=True,
        postgresql_where=sa.text(
            "is_preferred = true AND status = 'active'"
        ),
    )

    op.create_table(
        "payouts",
        sa.Column("host_node_id", sa.UUID(), nullable=False),
        sa.Column("payout_method_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column(
            "provider_reference",
            sa.String(180),
            nullable=False,
            server_default="",
        ),
        sa.Column("ledger_transaction_id", sa.UUID(), nullable=True),
        *_base_columns(),
        sa.CheckConstraint(
            "amount_minor > 0",
            name="ck_payout_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["host_node_id"],
            ["nodes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payout_method_id"],
            ["payout_methods.id"],
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
        "host_node_id",
        "payout_method_id",
        "status",
        "idempotency_key",
    ):
        op.create_index(
            f"ix_payouts_{col}",
            "payouts",
            [col],
        )

    op.create_table(
        "fx_conversions",
        sa.Column("source_currency", sa.String(3), nullable=False),
        sa.Column("target_currency", sa.String(3), nullable=False),
        sa.Column("source_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("target_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("rate_numerator", sa.BigInteger(), nullable=False),
        sa.Column("rate_denominator", sa.BigInteger(), nullable=False),
        sa.Column("rate_source", sa.String(120), nullable=False),
        sa.Column("source_transaction_id", sa.UUID(), nullable=False),
        sa.Column("target_transaction_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="posted",
        ),
        *_base_columns(),
        sa.CheckConstraint(
            "source_currency <> target_currency",
            name="ck_fx_currency_different",
        ),
        sa.CheckConstraint(
            "source_amount_minor > 0 AND target_amount_minor > 0",
            name="ck_fx_amounts_positive",
        ),
        sa.CheckConstraint(
            "rate_numerator > 0 AND rate_denominator > 0",
            name="ck_fx_rate_positive",
        ),
        sa.ForeignKeyConstraint(
            ["source_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_transaction_id"],
            ["ledger_transactions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_transaction_id"),
        sa.UniqueConstraint("target_transaction_id"),
    )

    op.create_table(
        "payment_reconciliation_events",
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("event_id", sa.String(180), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="accepted",
        ),
        sa.Column(
            "processed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_base_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "event_id",
            name="uq_payment_reconciliation_provider_event",
        ),
    )
    op.create_index(
        "ix_payment_reconciliation_events_status",
        "payment_reconciliation_events",
        ["status"],
    )

    # Posted ledger history is append-only. Financial corrections
    # must be represented by new reversal/adjustment transactions.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION khan_finance_block_ledger_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'KF-001 immutable ledger: UPDATE/DELETE is forbidden';
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_immutable
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW
        EXECUTE FUNCTION khan_finance_block_ledger_mutation();
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_ledger_transactions_immutable
        BEFORE UPDATE OR DELETE ON ledger_transactions
        FOR EACH ROW
        EXECUTE FUNCTION khan_finance_block_ledger_mutation();
        """
    )

    # Remove migration-only defaults from application-owned columns.
    for table, columns in {
        "financial_accounts": ("status", "metadata_json"),
        "ledger_transactions": (
            "status",
            "external_reference",
            "description",
            "metadata_json",
        ),
        "customer_wallets": ("status",),
        "host_settlement_accounts": ("status",),
        "payment_deposits": ("provider_reference", "status"),
        "usage_reservations": (
            "consumed_minor",
            "released_minor",
            "status",
            "reference_type",
            "reference_id",
        ),
        "host_earnings": ("status",),
        "payout_methods": ("last4", "is_preferred", "status"),
        "payouts": ("status", "provider_reference"),
        "fx_conversions": ("status",),
        "payment_reconciliation_events": (
            "status",
            "processed",
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
    # This downgrade is structurally safe because KF-001 refuses to
    # perform the upgrade while legacy plaintext token rows exist.
    # Do not downgrade after new encrypted token data has been created
    # without an explicit data-export/re-encryption procedure.
    op.drop_index(
        "ix_payment_method_tokens_token_fingerprint",
        table_name="payment_method_tokens",
    )
    op.drop_column(
        "payment_method_tokens",
        "token_fingerprint",
    )
    op.drop_column(
        "payment_method_tokens",
        "encryption_key_version",
    )
    op.alter_column(
        "payment_method_tokens",
        "encrypted_provider_token",
        new_column_name="provider_token",
        existing_type=sa.String(4096),
        type_=sa.String(255),
        existing_nullable=False,
    )

    op.execute(
        "DROP TRIGGER IF EXISTS trg_ledger_entries_immutable "
        "ON ledger_entries"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_ledger_transactions_immutable "
        "ON ledger_transactions"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "khan_finance_block_ledger_mutation()"
    )

    for table in (
        "payment_reconciliation_events",
        "fx_conversions",
        "payouts",
        "payout_methods",
        "host_earnings",
        "usage_reservations",
        "payment_deposits",
        "host_settlement_accounts",
        "customer_wallets",
        "ledger_entries",
        "ledger_transactions",
        "financial_accounts",
    ):
        op.drop_table(table)
