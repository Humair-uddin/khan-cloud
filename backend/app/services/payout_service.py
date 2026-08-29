from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.finance import (
    FinancialAccount,
    HostSettlementAccount,
    Payout,
    PayoutMethod,
)
from app.services.finance_crypto_service import (
    encrypt_financial_payload,
    financial_fingerprint,
)
from app.services.ledger_service import (
    LedgerLine,
    account_balance_minor,
    get_or_create_account,
    post_transaction,
)


class PayoutError(ValueError):
    pass


def create_payout_method(
    db: Session,
    *,
    host_node_id: UUID,
    method_type: str,
    provider: str,
    country_code: str,
    currency: str,
    destination_payload: dict,
    fingerprint_source: str,
    last4: str = "",
    preferred: bool = True,
) -> PayoutMethod:
    aad = f"khan-finance:payout:{host_node_id}"

    encrypted_payload, key_version = encrypt_financial_payload(
        destination_payload,
        aad=aad,
    )

    if preferred:
        db.execute(
            update(PayoutMethod)
            .where(
                PayoutMethod.host_node_id == host_node_id,
                PayoutMethod.is_preferred.is_(True),
            )
            .values(is_preferred=False)
        )

    method = PayoutMethod(
        host_node_id=host_node_id,
        method_type=method_type,
        provider=provider,
        country_code=country_code.upper(),
        currency=currency.upper(),
        encrypted_payload=encrypted_payload,
        encryption_key_version=key_version,
        fingerprint=financial_fingerprint(fingerprint_source),
        last4=last4[-4:],
        is_preferred=preferred,
        status="active",
    )

    db.add(method)
    db.flush()

    return method


def preferred_payout_method(
    db: Session,
    *,
    host_node_id: UUID,
) -> PayoutMethod:
    method = db.scalar(
        select(PayoutMethod).where(
            PayoutMethod.host_node_id == host_node_id,
            PayoutMethod.is_preferred.is_(True),
            PayoutMethod.status == "active",
        )
    )

    if method is None:
        raise PayoutError(
            "Host does not have an active preferred payout method."
        )

    return method


def queue_payout(
    db: Session,
    *,
    host_node_id: UUID,
    amount_minor: int,
    currency: str,
    idempotency_key: str,
) -> Payout:
    if amount_minor <= 0:
        raise PayoutError("Payout amount must be positive.")

    existing = db.scalar(
        select(Payout).where(
            Payout.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        if (
            existing.host_node_id != host_node_id
            or existing.amount_minor != amount_minor
            or existing.currency != currency
        ):
            raise PayoutError(
                "Payout idempotency key was reused "
                "with different contents."
            )
        return existing

    method = preferred_payout_method(
        db,
        host_node_id=host_node_id,
    )

    if method.currency != currency:
        raise PayoutError(
            "Payout method currency does not match host settlement currency."
        )

    settlement = db.scalar(
        select(HostSettlementAccount).where(
            HostSettlementAccount.host_node_id == host_node_id,
            HostSettlementAccount.currency == currency,
        )
    )

    if settlement is None:
        raise PayoutError("Host settlement account not found.")

    available = db.get(
        FinancialAccount,
        settlement.available_account_id,
    )

    if account_balance_minor(db, available) < amount_minor:
        raise PayoutError(
            "Host has insufficient available settlement balance."
        )

    payout_clearing = get_or_create_account(
        db,
        account_code=f"treasury:payout:{currency}:clearing",
        account_type="payout_clearing",
        normal_side="credit",
        currency=currency,
    )

    tx = post_transaction(
        db,
        transaction_type="payout_queued",
        currency=currency,
        idempotency_key=f"ledger:{idempotency_key}",
        lines=[
            LedgerLine(
                account=available,
                side="debit",
                amount_minor=amount_minor,
            ),
            LedgerLine(
                account=payout_clearing,
                side="credit",
                amount_minor=amount_minor,
            ),
        ],
    )

    payout = Payout(
        host_node_id=host_node_id,
        payout_method_id=method.id,
        currency=currency,
        amount_minor=amount_minor,
        status="queued",
        idempotency_key=idempotency_key,
        ledger_transaction_id=tx.id,
    )

    db.add(payout)
    db.flush()

    return payout


def mark_payout_processing(
    db: Session,
    *,
    payout: Payout,
    provider_reference: str,
) -> Payout:
    if payout.status != "queued":
        raise PayoutError(
            "Only queued payouts can enter processing."
        )

    if not provider_reference.strip():
        raise PayoutError(
            "Provider payout reference is required."
        )

    payout.status = "processing"
    payout.provider_reference = provider_reference.strip()

    db.flush()
    return payout


def mark_payout_paid(
    db: Session,
    *,
    payout: Payout,
    idempotency_key: str,
) -> Payout:
    if payout.status != "processing":
        raise PayoutError(
            "Only processing payouts can be marked paid."
        )

    payout_clearing = get_or_create_account(
        db,
        account_code=f"treasury:payout:{payout.currency}:clearing",
        account_type="payout_clearing",
        normal_side="credit",
        currency=payout.currency,
    )

    bank = get_or_create_account(
        db,
        account_code=f"treasury:bank:{payout.currency}",
        account_type="bank_asset",
        normal_side="debit",
        currency=payout.currency,
    )

    post_transaction(
        db,
        transaction_type="payout_paid",
        currency=payout.currency,
        idempotency_key=idempotency_key,
        lines=[
            LedgerLine(
                account=payout_clearing,
                side="debit",
                amount_minor=payout.amount_minor,
                memo="Clear payout payable",
            ),
            LedgerLine(
                account=bank,
                side="credit",
                amount_minor=payout.amount_minor,
                memo="Treasury funds paid to host",
            ),
        ],
        external_reference=payout.provider_reference,
    )

    payout.status = "paid"
    db.flush()

    return payout


def mark_payout_failed(
    db: Session,
    *,
    payout: Payout,
    idempotency_key: str,
    reason: str,
) -> Payout:
    if payout.status not in {"queued", "processing"}:
        raise PayoutError(
            "Only queued or processing payouts can fail."
        )

    if payout.ledger_transaction_id is None:
        raise PayoutError(
            "Payout reservation transaction is missing."
        )

    from app.services.ledger_service import reverse_transaction

    reverse_transaction(
        db,
        original_transaction_id=payout.ledger_transaction_id,
        idempotency_key=idempotency_key,
        reason=reason,
    )

    payout.status = "failed"
    db.flush()

    return payout
