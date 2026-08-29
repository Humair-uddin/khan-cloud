from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import (
    ChargebackDispute,
    CustomerWallet,
    FinancialAccount,
    Refund,
)
from app.services.ledger_service import (
    LedgerLine,
    account_balance_minor,
    get_or_create_account,
    post_transaction,
)


class RefundError(ValueError):
    pass


def queue_refund(
    db: Session,
    *,
    wallet: CustomerWallet,
    amount_minor: int,
    reason: str,
    idempotency_key: str,
    external_reference: str = "",
) -> Refund:
    if amount_minor <= 0:
        raise RefundError("Refund amount must be positive.")

    if not reason.strip():
        raise RefundError("Refund reason is required.")

    existing = db.scalar(
        select(Refund).where(
            Refund.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        if (
            existing.wallet_id != wallet.id
            or existing.currency != wallet.currency
            or existing.amount_minor != amount_minor
            or existing.reason != reason
            or existing.external_reference != external_reference
        ):
            raise RefundError(
                "Refund idempotency key was reused "
                "with different contents."
            )
        return existing

    available = db.get(
        FinancialAccount,
        wallet.available_account_id,
    )

    if account_balance_minor(db, available) < amount_minor:
        raise RefundError(
            "Customer has insufficient available balance for refund."
        )

    clearing = get_or_create_account(
        db,
        account_code=f"treasury:refund:{wallet.currency}:clearing",
        account_type="refund_clearing",
        normal_side="credit",
        currency=wallet.currency,
    )

    tx = post_transaction(
        db,
        transaction_type="customer_refund_queued",
        currency=wallet.currency,
        idempotency_key=f"ledger:{idempotency_key}",
        lines=[
            LedgerLine(
                account=available,
                side="debit",
                amount_minor=amount_minor,
                memo="Reduce customer wallet liability",
            ),
            LedgerLine(
                account=clearing,
                side="credit",
                amount_minor=amount_minor,
                memo="Refund payable/clearing",
            ),
        ],
        external_reference=external_reference,
        description=reason,
    )

    refund = Refund(
        organization_id=wallet.organization_id,
        wallet_id=wallet.id,
        currency=wallet.currency,
        amount_minor=amount_minor,
        status="queued",
        reason=reason,
        external_reference=external_reference,
        idempotency_key=idempotency_key,
        ledger_transaction_id=tx.id,
    )

    db.add(refund)
    db.flush()

    return refund


def post_chargeback(
    db: Session,
    *,
    wallet: CustomerWallet,
    provider: str,
    provider_dispute_id: str,
    amount_minor: int,
    reason: str = "",
) -> ChargebackDispute:
    if amount_minor <= 0:
        raise RefundError("Chargeback amount must be positive.")

    existing = db.scalar(
        select(ChargebackDispute).where(
            ChargebackDispute.provider == provider,
            ChargebackDispute.provider_dispute_id == provider_dispute_id,
        )
    )
    if existing is not None:
        if (
            existing.wallet_id != wallet.id
            or existing.organization_id != wallet.organization_id
            or existing.currency != wallet.currency
            or existing.amount_minor != amount_minor
            or existing.reason != reason
        ):
            raise RefundError(
                "Provider dispute ID was reused "
                "with different chargeback contents."
            )

        return existing

    available = db.get(
        FinancialAccount,
        wallet.available_account_id,
    )

    if account_balance_minor(db, available) < amount_minor:
        raise RefundError(
            "Customer wallet cannot absorb this chargeback."
        )

    clearing = get_or_create_account(
        db,
        account_code=f"treasury:{provider}:{wallet.currency}:clearing",
        account_type="gateway_clearing",
        normal_side="debit",
        currency=wallet.currency,
    )

    tx = post_transaction(
        db,
        transaction_type="payment_chargeback",
        currency=wallet.currency,
        idempotency_key=(
            f"chargeback:{provider}:{provider_dispute_id}"
        ),
        lines=[
            LedgerLine(
                account=available,
                side="debit",
                amount_minor=amount_minor,
                memo="Reduce customer wallet liability",
            ),
            LedgerLine(
                account=clearing,
                side="credit",
                amount_minor=amount_minor,
                memo="Provider chargeback against clearing asset",
            ),
        ],
        external_reference=provider_dispute_id,
        description=reason,
    )

    dispute = ChargebackDispute(
        organization_id=wallet.organization_id,
        wallet_id=wallet.id,
        provider=provider,
        provider_dispute_id=provider_dispute_id,
        currency=wallet.currency,
        amount_minor=amount_minor,
        status="posted",
        reason=reason,
        ledger_transaction_id=tx.id,
    )

    db.add(dispute)
    db.flush()

    return dispute
