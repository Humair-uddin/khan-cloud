from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import (
    FinancialAccount,
    FinancialAdjustment,
)
from app.services.ledger_service import (
    LedgerLine,
    post_transaction,
)


class AdjustmentError(ValueError):
    pass


def create_financial_adjustment(
    db: Session,
    *,
    debit_account: FinancialAccount,
    credit_account: FinancialAccount,
    amount_minor: int,
    adjustment_type: str,
    reason: str,
    actor_user_id: UUID | None,
    idempotency_key: str,
) -> FinancialAdjustment:
    if debit_account.id == credit_account.id:
        raise AdjustmentError(
            "Adjustment requires two different accounts."
        )

    if debit_account.currency != credit_account.currency:
        raise AdjustmentError(
            "Adjustment accounts must use the same currency."
        )

    if amount_minor <= 0:
        raise AdjustmentError(
            "Adjustment amount must be positive."
        )

    if not reason.strip():
        raise AdjustmentError(
            "Adjustment reason is required."
        )

    existing = db.scalar(
        select(FinancialAdjustment).where(
            FinancialAdjustment.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        if (
            existing.debit_account_id != debit_account.id
            or existing.credit_account_id != credit_account.id
            or existing.currency != debit_account.currency
            or existing.amount_minor != amount_minor
            or existing.adjustment_type != adjustment_type
            or existing.reason != reason
            or existing.actor_user_id != actor_user_id
        ):
            raise AdjustmentError(
                "Adjustment idempotency key was reused "
                "with different contents."
            )
        return existing

    tx = post_transaction(
        db,
        transaction_type=f"adjustment:{adjustment_type}",
        currency=debit_account.currency,
        idempotency_key=f"ledger:{idempotency_key}",
        lines=[
            LedgerLine(
                account=debit_account,
                side="debit",
                amount_minor=amount_minor,
                memo=reason,
            ),
            LedgerLine(
                account=credit_account,
                side="credit",
                amount_minor=amount_minor,
                memo=reason,
            ),
        ],
        description=reason,
        metadata_json={
            "actor_user_id": (
                str(actor_user_id)
                if actor_user_id is not None
                else None
            ),
            "adjustment_type": adjustment_type,
        },
    )

    adjustment = FinancialAdjustment(
        adjustment_type=adjustment_type,
        debit_account_id=debit_account.id,
        credit_account_id=credit_account.id,
        currency=debit_account.currency,
        amount_minor=amount_minor,
        reason=reason,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
        ledger_transaction_id=tx.id,
    )

    db.add(adjustment)
    db.flush()

    return adjustment
