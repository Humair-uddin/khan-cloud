from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


SUPPORTED_FINANCE_CURRENCIES = ("PKR", "USD")


class FinancialAccount(BaseModel):
    """
    Canonical chart-of-accounts node.

    Balances are NEVER authoritative columns on this model.
    Account balances are derived from immutable posted ledger entries.
    """

    __tablename__ = "financial_accounts"

    account_code: Mapped[str] = mapped_column(
        String(180),
        unique=True,
        index=True,
        nullable=False,
    )
    account_type: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
    )
    normal_side: Mapped[str] = mapped_column(
        String(6),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        index=True,
        nullable=False,
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    host_node_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
        nullable=False,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "normal_side IN ('debit','credit')",
            name="ck_financial_accounts_normal_side",
        ),
        CheckConstraint(
            "currency IN ('PKR','USD')",
            name="ck_financial_accounts_currency",
        ),
    )


class LedgerTransaction(BaseModel):
    """
    Immutable accounting transaction header.

    A posted transaction is never edited or deleted.
    Corrections are represented by reversal transactions.
    """

    __tablename__ = "ledger_transactions"

    transaction_type: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="posted",
        index=True,
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(180),
        unique=True,
        index=True,
        nullable=False,
    )

    request_hash: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )

    external_reference: Mapped[str] = mapped_column(
        String(255),
        default="",
        index=True,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(500),
        default="",
        nullable=False,
    )

    reversed_transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "currency IN ('PKR','USD')",
            name="ck_ledger_transactions_currency",
        ),
        CheckConstraint(
            "status IN ('posted','reversed')",
            name="ck_ledger_transactions_status",
        ),
    )


class LedgerEntry(BaseModel):
    __tablename__ = "ledger_entries"

    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    side: Mapped[str] = mapped_column(
        String(6),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    memo: Mapped[str] = mapped_column(
        String(255),
        default="",
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "side IN ('debit','credit')",
            name="ck_ledger_entries_side",
        ),
        CheckConstraint(
            "amount_minor > 0",
            name="ck_ledger_entries_positive_amount",
        ),
    )


class CustomerWallet(BaseModel):
    """
    Customer-wallet product facade.

    The actual monetary authority is the pair of financial accounts.
    """

    __tablename__ = "customer_wallets"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        index=True,
        nullable=False,
    )

    available_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    reserved_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "currency",
            name="uq_customer_wallet_org_currency",
        ),
        CheckConstraint(
            "currency IN ('PKR','USD')",
            name="ck_customer_wallet_currency",
        ),
    )


class HostSettlementAccount(BaseModel):
    __tablename__ = "host_settlement_accounts"

    host_node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        index=True,
        nullable=False,
    )

    pending_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    held_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    available_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "host_node_id",
            "currency",
            name="uq_host_settlement_node_currency",
        ),
        CheckConstraint(
            "currency IN ('PKR','USD')",
            name="ck_host_settlement_currency",
        ),
    )


class PaymentDeposit(BaseModel):
    __tablename__ = "payment_deposits"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    provider: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
    )
    provider_event_id: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )
    provider_reference: Mapped[str] = mapped_column(
        String(180),
        default="",
        index=True,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="confirmed",
        index=True,
        nullable=False,
    )

    ledger_transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_payment_deposit_provider_event",
        ),
        CheckConstraint(
            "amount_minor > 0",
            name="ck_payment_deposit_amount_positive",
        ),
    )


class UsageReservation(BaseModel):
    __tablename__ = "usage_reservations"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    wallet_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_wallets.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    reserved_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    consumed_minor: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    released_minor: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="reserved",
        index=True,
        nullable=False,
    )

    reference_type: Mapped[str] = mapped_column(
        String(80),
        default="",
        index=True,
        nullable=False,
    )
    reference_id: Mapped[str] = mapped_column(
        String(180),
        default="",
        index=True,
        nullable=False,
    )

    reserve_transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "reserved_minor > 0",
            name="ck_usage_reservation_positive",
        ),
        CheckConstraint(
            "consumed_minor >= 0",
            name="ck_usage_reservation_consumed_nonnegative",
        ),
        CheckConstraint(
            "released_minor >= 0",
            name="ck_usage_reservation_released_nonnegative",
        ),
        CheckConstraint(
            "consumed_minor + released_minor <= reserved_minor",
            name="ck_usage_reservation_allocation",
        ),
    )


class HostEarning(BaseModel):
    __tablename__ = "host_earnings"

    host_node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    usage_reservation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("usage_reservations.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    gross_charge_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    host_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    platform_revenue_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
        nullable=False,
    )

    earning_transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "gross_charge_minor > 0",
            name="ck_host_earning_gross_positive",
        ),
        CheckConstraint(
            "host_amount_minor >= 0",
            name="ck_host_earning_host_nonnegative",
        ),
        CheckConstraint(
            "platform_revenue_minor >= 0",
            name="ck_host_earning_revenue_nonnegative",
        ),
        CheckConstraint(
            "host_amount_minor + platform_revenue_minor = gross_charge_minor",
            name="ck_host_earning_split_balanced",
        ),
    )


class PayoutMethod(BaseModel):
    __tablename__ = "payout_methods"

    host_node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    method_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )
    country_code: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    encrypted_payload: Mapped[str] = mapped_column(
        String(4096),
        nullable=False,
    )
    encryption_key_version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    fingerprint: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )
    last4: Mapped[str] = mapped_column(
        String(4),
        default="",
        nullable=False,
    )

    is_preferred: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
        nullable=False,
    )


class Payout(BaseModel):
    __tablename__ = "payouts"

    host_node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    payout_method_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payout_methods.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="queued",
        index=True,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(180),
        unique=True,
        index=True,
        nullable=False,
    )

    provider_reference: Mapped[str] = mapped_column(
        String(180),
        default="",
        nullable=False,
    )

    ledger_transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )

    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0",
            name="ck_payout_amount_positive",
        ),
    )


class FxConversion(BaseModel):
    __tablename__ = "fx_conversions"

    source_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    target_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    source_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    target_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    rate_numerator: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    rate_denominator: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    rate_source: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    source_transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    target_transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="posted",
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "source_currency <> target_currency",
            name="ck_fx_currency_different",
        ),
        CheckConstraint(
            "source_amount_minor > 0 AND target_amount_minor > 0",
            name="ck_fx_amounts_positive",
        ),
        CheckConstraint(
            "rate_numerator > 0 AND rate_denominator > 0",
            name="ck_fx_rate_positive",
        ),
    )


class PaymentReconciliationEvent(BaseModel):
    __tablename__ = "payment_reconciliation_events"

    provider: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )
    event_id: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )
    event_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="accepted",
        index=True,
        nullable=False,
    )

    processed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    reconciliation_type: Mapped[str] = mapped_column(
        String(40),
        default="provider_event",
        nullable=False,
    )

    outcome: Mapped[str] = mapped_column(
        String(30),
        default="pending_review",
        index=True,
        nullable=False,
    )

    provider_amount_minor: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    internal_amount_minor: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    provider_currency: Mapped[str] = mapped_column(
        String(3),
        default="",
        nullable=False,
    )

    internal_currency: Mapped[str] = mapped_column(
        String(3),
        default="",
        nullable=False,
    )

    internal_resource_type: Mapped[str] = mapped_column(
        String(50),
        default="",
        nullable=False,
    )

    internal_resource_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )

    resolution_reason: Mapped[str] = mapped_column(
        String(500),
        default="",
        nullable=False,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "event_id",
            name="uq_payment_reconciliation_provider_event",
        ),
        CheckConstraint(
            "outcome IN "
            "('matched','amount_mismatch','currency_mismatch',"
            "'missing_internal','missing_provider',"
            "'duplicate_provider','pending_review','resolved')",
            name="ck_payment_reconciliation_outcome",
        ),
    )


class Refund(BaseModel):
    __tablename__ = "finance_refunds"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    wallet_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_wallets.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="queued",
        index=True,
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    external_reference: Mapped[str] = mapped_column(
        String(180),
        default="",
        index=True,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(180),
        unique=True,
        index=True,
        nullable=False,
    )

    ledger_transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0",
            name="ck_finance_refund_amount_positive",
        ),
    )


class ChargebackDispute(BaseModel):
    __tablename__ = "chargeback_disputes"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    wallet_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customer_wallets.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
    )
    provider_dispute_id: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    resolution_reference: Mapped[str] = mapped_column(
        String(180),
        default="",
        nullable=False,
    )

    resolution_reason: Mapped[str] = mapped_column(
        String(500),
        default="",
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="posted",
        index=True,
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        String(500),
        default="",
        nullable=False,
    )

    ledger_transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_dispute_id",
            name="uq_chargeback_provider_dispute",
        ),
        CheckConstraint(
            "amount_minor > 0",
            name="ck_chargeback_amount_positive",
        ),
    )


class FinancialAdjustment(BaseModel):
    __tablename__ = "financial_adjustments"

    adjustment_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
    )

    debit_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    credit_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("financial_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(180),
        unique=True,
        index=True,
        nullable=False,
    )

    ledger_transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0",
            name="ck_financial_adjustment_amount_positive",
        ),
        CheckConstraint(
            "debit_account_id <> credit_account_id",
            name="ck_financial_adjustment_accounts_different",
        ),
    )


class TreasurySettlementBatch(BaseModel):
    __tablename__ = "treasury_settlement_batches"

    settlement_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        index=True,
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="posted",
        index=True,
        nullable=False,
    )

    external_reference: Mapped[str] = mapped_column(
        String(180),
        default="",
        index=True,
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(180),
        unique=True,
        index=True,
        nullable=False,
    )

    ledger_transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("ledger_transactions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0",
            name="ck_treasury_settlement_amount_positive",
        ),
    )
