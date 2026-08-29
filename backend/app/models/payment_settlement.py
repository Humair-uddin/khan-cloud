from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import (
    JSONB,
    UUID as PGUUID,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PaymentProviderSettlementBatch(BaseModel):
    __tablename__ = "payment_provider_settlement_batches"

    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "payment_providers.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    provider_code: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
    )

    provider_settlement_reference: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    settlement_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        index=True,
    )

    gross_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    fee_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    net_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    settlement_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="received",
        nullable=False,
        index=True,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
        unique=True,
        index=True,
    )

    credential_reference_snapshot: Mapped[str] = mapped_column(
        String(240),
        default="",
        nullable=False,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "provider_settlement_reference",
            name="uq_payment_provider_settlement_reference",
        ),
        CheckConstraint(
            "gross_amount_minor >= 0",
            name="ck_payment_provider_settlement_gross",
        ),
        CheckConstraint(
            "fee_amount_minor >= 0",
            name="ck_payment_provider_settlement_fee",
        ),
        CheckConstraint(
            "net_amount_minor = "
            "gross_amount_minor - fee_amount_minor",
            name="ck_payment_provider_settlement_net",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_payment_provider_settlement_hash",
        ),
        CheckConstraint(
            "status IN "
            "('received','reconciling','reconciled',"
            "'pending_review','failed')",
            name="ck_payment_provider_settlement_status",
        ),
    )


class PaymentProviderSettlementItem(BaseModel):
    __tablename__ = "payment_provider_settlement_items"

    settlement_batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "payment_provider_settlement_batches.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    provider_line_id: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    provider_transaction_reference: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    presentment_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    settlement_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    gross_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    fee_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )

    net_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    explicit_fx_transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    reconciliation_status: Mapped[str] = mapped_column(
        String(30),
        default="pending_review",
        nullable=False,
        index=True,
    )

    reconciliation_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "payment_reconciliation_events.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
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

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "settlement_batch_id",
            "provider_line_id",
            name="uq_payment_provider_settlement_line",
        ),
        CheckConstraint(
            "gross_amount_minor >= 0",
            name="ck_payment_provider_settlement_item_gross",
        ),
        CheckConstraint(
            "fee_amount_minor >= 0",
            name="ck_payment_provider_settlement_item_fee",
        ),
        CheckConstraint(
            "net_amount_minor = "
            "gross_amount_minor - fee_amount_minor",
            name="ck_payment_provider_settlement_item_net",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_payment_provider_settlement_item_hash",
        ),
        CheckConstraint(
            "reconciliation_status IN "
            "('matched','amount_mismatch','currency_mismatch',"
            "'missing_internal','missing_provider',"
            "'duplicate_provider','pending_review','resolved')",
            name="ck_payment_provider_settlement_item_reconciliation",
        ),
        Index(
            "ix_pp_settle_item_txn_ref",
            "provider_transaction_reference",
        ),
        Index(
            "ix_payment_provider_settlement_item_reference",
            "settlement_batch_id",
            "provider_transaction_reference",
        ),
    )
