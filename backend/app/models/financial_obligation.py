from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class CustomerFinancialObligation(BaseModel):
    """
    Explicit customer receivable/debt projection.

    The canonical economic truth remains the immutable ledger.
    This row gives operations a domain projection for obligations
    created when an external loss cannot be fully absorbed by the
    customer's remaining wallet liability.
    """

    __tablename__ = "customer_financial_obligations"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=False,
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        index=True,
        nullable=True,
    )

    wallet_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "customer_wallets.id",
            ondelete="RESTRICT",
        ),
        index=True,
        nullable=False,
    )

    chargeback_dispute_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "chargeback_disputes.id",
            ondelete="RESTRICT",
        ),
        unique=True,
        nullable=False,
    )

    receivable_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "financial_accounts.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )

    provider_reference: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    original_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    outstanding_amount_minor: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="outstanding",
        index=True,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_reference",
            name="uq_customer_obligation_provider_reference",
        ),
        CheckConstraint(
            "original_amount_minor > 0",
            name="ck_customer_obligation_original_positive",
        ),
        CheckConstraint(
            "outstanding_amount_minor >= 0",
            name="ck_customer_obligation_outstanding_nonnegative",
        ),
        CheckConstraint(
            "outstanding_amount_minor <= original_amount_minor",
            name="ck_customer_obligation_outstanding_lte_original",
        ),
    )
