from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import (
    ChargebackDispute,
    CustomerWallet,
    FinancialAccount,
)
from app.models.financial_obligation import (
    CustomerFinancialObligation,
    CustomerObligationPayment,
)
from app.services.ledger_service import (
    LedgerLine,
    account_balance_minor,
    post_transaction,
)


class FinancialObligationError(ValueError):
    pass


def _normalize_currency(value: str) -> str:
    value = str(value or "").strip().upper()

    if (
        len(value) != 3
        or not value.isalpha()
    ):
        raise FinancialObligationError(
            "A valid three-letter currency is required."
        )

    return value


def _refresh_obligation_status(
    obligation: CustomerFinancialObligation,
) -> None:
    if obligation.outstanding_amount_minor == 0:
        obligation.status = "paid"
    elif (
        obligation.outstanding_amount_minor
        < obligation.original_amount_minor
    ):
        obligation.status = "partially_paid"
    else:
        obligation.status = "outstanding"


def collect_obligation_from_wallet(
    db: Session,
    *,
    obligation: CustomerFinancialObligation,
    amount_minor: int,
    idempotency_key: str,
    external_reference: str = "",
) -> CustomerObligationPayment:
    if amount_minor <= 0:
        raise FinancialObligationError(
            "Obligation collection amount must be positive."
        )

    idempotency_key = str(
        idempotency_key or ""
    ).strip()

    if not idempotency_key:
        raise FinancialObligationError(
            "Obligation collection idempotency key is required."
        )

    existing = db.scalar(
        select(CustomerObligationPayment).where(
            CustomerObligationPayment.idempotency_key
            == idempotency_key
        )
    )

    if existing is not None:
        if (
            existing.obligation_id != obligation.id
            or existing.amount_minor != amount_minor
            or existing.currency != obligation.currency
            or existing.external_reference
            != external_reference
        ):
            raise FinancialObligationError(
                "Obligation collection idempotency key was reused with different contents."
            )

        return existing

    if obligation.status == "paid":
        raise FinancialObligationError(
            "Obligation is already fully paid."
        )

    if amount_minor > obligation.outstanding_amount_minor:
        raise FinancialObligationError(
            "Collection exceeds obligation outstanding amount."
        )

    wallet = db.get(
        CustomerWallet,
        obligation.wallet_id,
    )

    if wallet is None:
        raise FinancialObligationError(
            "Customer wallet was not found."
        )

    currency = _normalize_currency(
        obligation.currency
    )

    if _normalize_currency(wallet.currency) != currency:
        raise FinancialObligationError(
            "Cross-currency obligation collection requires an explicit FX transaction."
        )

    available = db.get(
        FinancialAccount,
        wallet.available_account_id,
    )

    receivable = db.get(
        FinancialAccount,
        obligation.receivable_account_id,
    )

    if available is None or receivable is None:
        raise FinancialObligationError(
            "Obligation ledger accounts are missing."
        )

    if account_balance_minor(
        db,
        available,
    ) < amount_minor:
        raise FinancialObligationError(
            "Customer wallet has insufficient available balance."
        )

    tx = post_transaction(
        db,
        transaction_type="customer_obligation_collection",
        currency=currency,
        idempotency_key=(
            f"obligation:{idempotency_key}"
        ),
        lines=[
            LedgerLine(
                account=available,
                side="debit",
                amount_minor=amount_minor,
                memo="Apply wallet liability to customer obligation",
            ),
            LedgerLine(
                account=receivable,
                side="credit",
                amount_minor=amount_minor,
                memo="Reduce customer receivable",
            ),
        ],
        external_reference=external_reference,
        metadata_json={
            "obligation_id": str(obligation.id),
        },
    )

    obligation.outstanding_amount_minor -= amount_minor

    if obligation.outstanding_amount_minor < 0:
        raise FinancialObligationError(
            "Obligation outstanding amount cannot become negative."
        )

    _refresh_obligation_status(
        obligation
    )

    payment = CustomerObligationPayment(
        obligation_id=obligation.id,
        organization_id=obligation.organization_id,
        wallet_id=obligation.wallet_id,
        amount_minor=amount_minor,
        currency=currency,
        payment_type="collection",
        idempotency_key=idempotency_key,
        ledger_transaction_id=tx.id,
        external_reference=external_reference,
    )

    db.add(payment)
    db.flush()

    return payment


def resolve_chargeback_dispute(
    db: Session,
    *,
    dispute: ChargebackDispute,
    outcome: str,
    provider_reference: str,
    reason: str,
    idempotency_key: str,
) -> ChargebackDispute:
    outcome = str(outcome or "").strip().lower()
    provider_reference = str(
        provider_reference or ""
    ).strip()
    reason = str(reason or "").strip()
    idempotency_key = str(
        idempotency_key or ""
    ).strip()

    if outcome not in {
        "won",
        "lost",
        "reversed",
    }:
        raise FinancialObligationError(
            "Chargeback outcome must be won, lost, or reversed."
        )

    if not provider_reference:
        raise FinancialObligationError(
            "Chargeback resolution provider reference is required."
        )

    if not idempotency_key:
        raise FinancialObligationError(
            "Chargeback resolution idempotency key is required."
        )

    if dispute.status in {
        "won",
        "lost",
        "reversed",
    }:
        if (
            dispute.status != outcome
            or dispute.resolution_reference
            != provider_reference
            or dispute.resolution_reason != reason
        ):
            raise FinancialObligationError(
                "Resolved chargeback was replayed "
                "with different contents."
            )

        return dispute

    if dispute.status not in {
        "open",
        "created",
    }:
        raise FinancialObligationError(
            "Chargeback cannot be resolved from its current state."
        )

    obligation = db.scalar(
        select(CustomerFinancialObligation).where(
            CustomerFinancialObligation.chargeback_dispute_id
            == dispute.id
        )
    )

    if outcome in {
        "won",
        "reversed",
    }:
        #
        # Provider returned/released the disputed funds.
        # Reverse the remaining customer receivable only.
        # Amount already collected from the customer remains a
        # separate historical ledger event and is not silently
        # rewritten.
        #
        if (
            obligation is not None
            and obligation.outstanding_amount_minor > 0
        ):
            receivable = db.get(
                FinancialAccount,
                obligation.receivable_account_id,
            )

            if receivable is None:
                raise FinancialObligationError(
                    "Customer receivable account is missing."
                )

            from app.services.ledger_service import (
                get_or_create_account,
            )

            clearing = get_or_create_account(
                db,
                account_code=(
                    f"treasury:{dispute.provider}:"
                    f"{dispute.currency}:clearing"
                ),
                account_type="gateway_clearing",
                normal_side="debit",
                currency=dispute.currency,
            )

            amount = (
                obligation.outstanding_amount_minor
            )

            post_transaction(
                db,
                transaction_type="chargeback_recovery",
                currency=dispute.currency,
                idempotency_key=(
                    f"chargeback-resolution:{idempotency_key}"
                ),
                lines=[
                    LedgerLine(
                        account=clearing,
                        side="debit",
                        amount_minor=amount,
                        memo="Provider chargeback recovery",
                    ),
                    LedgerLine(
                        account=receivable,
                        side="credit",
                        amount_minor=amount,
                        memo="Release customer receivable",
                    ),
                ],
                external_reference=provider_reference,
                metadata_json={
                    "chargeback_dispute_id": str(dispute.id),
                    "outcome": outcome,
                },
            )

            obligation.outstanding_amount_minor = 0
            obligation.status = "paid"

    #
    # Lost means the provider loss stands; collectible receivable
    # remains unchanged.
    #
    dispute.status = outcome
    dispute.resolution_reference = provider_reference
    dispute.resolution_reason = reason

    db.flush()

    return dispute
