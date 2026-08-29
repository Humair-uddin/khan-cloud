"""
KF-001 compatibility facade.

Legacy BillingWallet is retained temporarily as a read/projection facade.
The canonical source of truth is the immutable financial ledger.
"""

from sqlalchemy.orm import Session

from app.services.wallet_service import (
    confirm_deposit,
    wallet_balances,
)


def ledger_authoritative_topup(
    db: Session,
    *,
    organization_id,
    user_id,
    currency: str,
    amount_minor: int,
    provider: str,
    provider_reference: str,
):
    if not provider_reference.strip():
        raise ValueError(
            "A unique payment provider/reference ID is required "
            "for a ledger-authoritative wallet credit."
        )

    provider_event_id = provider_reference.strip()

    wallet, deposit = confirm_deposit(
        db,
        organization_id=organization_id,
        user_id=user_id,
        currency=currency,
        amount_minor=amount_minor,
        provider=provider,
        provider_event_id=provider_event_id,
        provider_reference=provider_reference,
    )

    balances = wallet_balances(db, wallet)

    return wallet, deposit, balances
