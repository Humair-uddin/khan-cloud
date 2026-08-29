from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import (
    ChargebackDispute,
    CustomerWallet,
    FinancialAccount,
    Refund,
)
from app.models.financial_obligation import (
    CustomerFinancialObligation,
)
from app.services.ledger_service import (
    LedgerLine,
    account_balance_minor,
    get_or_create_account,
    post_transaction,
    reverse_transaction,
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
        raise RefundError(
            "Refund amount must be positive."
        )

    reason = reason.strip()

    if not reason:
        raise RefundError(
            "Refund reason is required."
        )

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
            or existing.external_reference
            != external_reference
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

    if available is None:
        raise RefundError(
            "Customer wallet available account is missing."
        )

    if account_balance_minor(
        db,
        available,
    ) < amount_minor:
        raise RefundError(
            "Customer has insufficient available "
            "balance for refund."
        )

    clearing = get_or_create_account(
        db,
        account_code=(
            f"treasury:refund:{wallet.currency}:clearing"
        ),
        account_type="refund_clearing",
        normal_side="credit",
        currency=wallet.currency,
    )

    transaction = post_transaction(
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
        ledger_transaction_id=transaction.id,
    )

    db.add(refund)
    db.flush()

    return refund


def mark_refund_processing(
    db: Session,
    *,
    refund: Refund,
    provider_reference: str,
) -> Refund:
    provider_reference = provider_reference.strip()

    if not provider_reference:
        raise RefundError(
            "Provider refund reference is required."
        )

    if refund.status == "paid":
        if (
            refund.external_reference
            and refund.external_reference
            != provider_reference
        ):
            raise RefundError(
                "Paid refund has a different "
                "provider reference."
            )

        return refund

    if refund.status == "processing":
        if (
            refund.external_reference
            != provider_reference
        ):
            raise RefundError(
                "Processing refund was replayed "
                "with a different provider reference."
            )

        return refund

    if refund.status != "queued":
        raise RefundError(
            "Only queued refunds can enter processing."
        )

    if (
        refund.external_reference
        and refund.external_reference
        != provider_reference
    ):
        raise RefundError(
            "Refund provider reference conflicts "
            "with its existing external reference."
        )

    refund.external_reference = provider_reference
    refund.status = "processing"

    db.flush()
    return refund


def mark_refund_paid(
    db: Session,
    *,
    refund: Refund,
    idempotency_key: str,
    provider_reference: str,
) -> Refund:
    provider_reference = provider_reference.strip()

    if not provider_reference:
        raise RefundError(
            "Provider refund reference is required."
        )

    if refund.status == "paid":
        if (
            refund.external_reference
            != provider_reference
        ):
            raise RefundError(
                "Paid refund was replayed with "
                "a different provider reference."
            )

        return refund

    if refund.status == "queued":
        mark_refund_processing(
            db,
            refund=refund,
            provider_reference=provider_reference,
        )

    if refund.status != "processing":
        raise RefundError(
            "Only queued or processing refunds "
            "can be marked paid."
        )

    if (
        refund.external_reference
        != provider_reference
    ):
        raise RefundError(
            "Refund provider reference changed "
            "during processing."
        )

    clearing = get_or_create_account(
        db,
        account_code=(
            f"treasury:refund:{refund.currency}:clearing"
        ),
        account_type="refund_clearing",
        normal_side="credit",
        currency=refund.currency,
    )

    bank = get_or_create_account(
        db,
        account_code=(
            f"treasury:bank:{refund.currency}"
        ),
        account_type="bank_asset",
        normal_side="debit",
        currency=refund.currency,
    )

    post_transaction(
        db,
        transaction_type="customer_refund_paid",
        currency=refund.currency,
        idempotency_key=idempotency_key,
        lines=[
            LedgerLine(
                account=clearing,
                side="debit",
                amount_minor=refund.amount_minor,
                memo="Clear refund payable",
            ),
            LedgerLine(
                account=bank,
                side="credit",
                amount_minor=refund.amount_minor,
                memo="Treasury funds returned to customer",
            ),
        ],
        external_reference=provider_reference,
        description=refund.reason,
    )

    refund.status = "paid"
    db.flush()

    return refund


def mark_refund_failed(
    db: Session,
    *,
    refund: Refund,
    idempotency_key: str,
    reason: str,
) -> Refund:
    if refund.status == "failed":
        return refund

    if refund.status == "paid":
        raise RefundError(
            "A paid refund cannot be failed."
        )

    if refund.status not in {
        "queued",
        "processing",
    }:
        raise RefundError(
            "Refund cannot fail from its current state."
        )

    if refund.ledger_transaction_id is None:
        raise RefundError(
            "Refund queue transaction is missing."
        )

    reverse_transaction(
        db,
        original_transaction_id=(
            refund.ledger_transaction_id
        ),
        idempotency_key=idempotency_key,
        reason=(
            reason.strip()
            or "Provider refund failed."
        ),
    )

    refund.status = "failed"
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
    provider = provider.strip().lower()
    provider_dispute_id = (
        provider_dispute_id.strip()
    )
    reason = reason.strip()

    if amount_minor <= 0:
        raise RefundError(
            "Chargeback amount must be positive."
        )

    if not provider:
        raise RefundError(
            "Chargeback provider is required."
        )

    if not provider_dispute_id:
        raise RefundError(
            "Provider dispute ID is required."
        )

    existing = db.scalar(
        select(ChargebackDispute).where(
            ChargebackDispute.provider == provider,
            ChargebackDispute.provider_dispute_id
            == provider_dispute_id,
        )
    )

    if existing is not None:
        if (
            existing.wallet_id != wallet.id
            or existing.organization_id
            != wallet.organization_id
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

    if available is None:
        raise RefundError(
            "Customer wallet available account is missing."
        )

    wallet_balance = max(
        account_balance_minor(
            db,
            available,
        ),
        0,
    )

    wallet_absorption = min(
        wallet_balance,
        amount_minor,
    )

    receivable_amount = (
        amount_minor - wallet_absorption
    )

    clearing = get_or_create_account(
        db,
        account_code=(
            f"treasury:{provider}:"
            f"{wallet.currency}:clearing"
        ),
        account_type="gateway_clearing",
        normal_side="debit",
        currency=wallet.currency,
    )

    lines: list[LedgerLine] = []

    if wallet_absorption:
        lines.append(
            LedgerLine(
                account=available,
                side="debit",
                amount_minor=wallet_absorption,
                memo=(
                    "Absorb chargeback from "
                    "customer wallet liability"
                ),
            )
        )

    receivable = None

    if receivable_amount:
        receivable = get_or_create_account(
            db,
            account_code=(
                f"receivable:customer:"
                f"{wallet.id}:{wallet.currency}"
            ),
            account_type="customer_receivable",
            normal_side="debit",
            currency=wallet.currency,
            organization_id=wallet.organization_id,
            user_id=wallet.user_id,
            metadata_json={
                "wallet_id": str(wallet.id),
                "purpose": "customer_financial_obligation",
            },
        )

        lines.append(
            LedgerLine(
                account=receivable,
                side="debit",
                amount_minor=receivable_amount,
                memo=(
                    "Record customer receivable "
                    "for chargeback shortfall"
                ),
            )
        )

    lines.append(
        LedgerLine(
            account=clearing,
            side="credit",
            amount_minor=amount_minor,
            memo=(
                "Provider chargeback against "
                "clearing asset"
            ),
        )
    )

    transaction = post_transaction(
        db,
        transaction_type="payment_chargeback",
        currency=wallet.currency,
        idempotency_key=(
            f"chargeback:{provider}:"
            f"{provider_dispute_id}"
        ),
        lines=lines,
        external_reference=provider_dispute_id,
        description=reason,
        metadata_json={
            "wallet_absorption_minor": (
                wallet_absorption
            ),
            "receivable_minor": (
                receivable_amount
            ),
        },
    )

    dispute = ChargebackDispute(
        organization_id=wallet.organization_id,
        wallet_id=wallet.id,
        provider=provider,
        provider_dispute_id=provider_dispute_id,
        currency=wallet.currency,
        amount_minor=amount_minor,
        status=(
            "posted_with_receivable"
            if receivable_amount
            else "posted"
        ),
        reason=reason,
        ledger_transaction_id=transaction.id,
    )

    db.add(dispute)
    db.flush()

    if receivable_amount:
        if receivable is None:
            raise RefundError(
                "Customer receivable account "
                "was not created."
            )

        obligation = CustomerFinancialObligation(
            organization_id=wallet.organization_id,
            user_id=wallet.user_id,
            wallet_id=wallet.id,
            chargeback_dispute_id=dispute.id,
            receivable_account_id=receivable.id,
            provider=provider,
            provider_reference=provider_dispute_id,
            currency=wallet.currency,
            original_amount_minor=receivable_amount,
            outstanding_amount_minor=receivable_amount,
            status="outstanding",
        )

        db.add(obligation)
        db.flush()

    return dispute
