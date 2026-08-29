from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import TreasurySettlementBatch
from app.services.ledger_service import (
    LedgerLine,
    get_or_create_account,
    post_transaction,
)


class TreasuryError(ValueError):
    pass


def settle_gateway_clearing_to_bank(
    db: Session,
    *,
    provider: str,
    currency: str,
    amount_minor: int,
    external_reference: str,
    idempotency_key: str,
) -> TreasurySettlementBatch:
    if amount_minor <= 0:
        raise TreasuryError(
            "Treasury settlement amount must be positive."
        )

    if not external_reference.strip():
        raise TreasuryError(
            "Treasury settlement reference is required."
        )

    existing = db.scalar(
        select(TreasurySettlementBatch).where(
            TreasurySettlementBatch.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        if (
            existing.provider != provider
            or existing.currency != currency
            or existing.amount_minor != amount_minor
            or existing.external_reference != external_reference
        ):
            raise TreasuryError(
                "Treasury idempotency key was reused "
                "with different contents."
            )
        return existing

    clearing = get_or_create_account(
        db,
        account_code=f"treasury:{provider}:{currency}:clearing",
        account_type="gateway_clearing",
        normal_side="debit",
        currency=currency,
    )

    bank = get_or_create_account(
        db,
        account_code=f"treasury:bank:{currency}",
        account_type="bank_asset",
        normal_side="debit",
        currency=currency,
    )

    tx = post_transaction(
        db,
        transaction_type="gateway_bank_settlement",
        currency=currency,
        idempotency_key=f"ledger:{idempotency_key}",
        lines=[
            LedgerLine(
                account=bank,
                side="debit",
                amount_minor=amount_minor,
                memo="Funds received into treasury bank",
            ),
            LedgerLine(
                account=clearing,
                side="credit",
                amount_minor=amount_minor,
                memo="Clear gateway receivable",
            ),
        ],
        external_reference=external_reference,
    )

    batch = TreasurySettlementBatch(
        settlement_type="gateway_to_bank",
        provider=provider,
        currency=currency,
        amount_minor=amount_minor,
        status="posted",
        external_reference=external_reference,
        idempotency_key=idempotency_key,
        ledger_transaction_id=tx.id,
        metadata_json={},
    )

    db.add(batch)
    db.flush()

    return batch
