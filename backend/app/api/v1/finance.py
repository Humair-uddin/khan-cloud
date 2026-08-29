from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.finance import CustomerWallet
from app.models.user import User
from app.schemas.finance import (
    FinanceDepositCreate,
    FinanceReservationCreate,
    FinanceWalletRead,
    FinancialAdjustmentCreate,
    RefundCreate,
    TreasurySettlementCreate,
    ProviderSettlementFetchCreate,
    ReconciliationResolutionCreate,
    ProviderCorridorCheck,
)
from app.services.wallet_service import (
    WalletError,
    confirm_deposit,
    reserve_funds,
    wallet_balances,
)


router = APIRouter(
    prefix="/finance",
    tags=["finance"],
)


@router.post(
    "/operator/deposits/confirm",
    response_model=FinanceWalletRead,
)
def confirm_customer_deposit(
    payload: FinanceDepositCreate,
    user: User = Depends(
        require_permission("finance.deposits.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        wallet, _ = confirm_deposit(
            db,
            organization_id=payload.organization_id,
            user_id=None,
            currency=payload.currency,
            amount_minor=payload.amount_minor,
            provider=payload.provider,
            provider_event_id=payload.provider_event_id,
            provider_reference=payload.provider_reference,
        )

        db.commit()

        balances = wallet_balances(db, wallet)

        return FinanceWalletRead(
            wallet_id=wallet.id,
            organization_id=wallet.organization_id,
            currency=wallet.currency,
            **balances,
        )
    except WalletError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get(
    "/operator/wallets/{wallet_id}",
    response_model=FinanceWalletRead,
)
def read_wallet(
    wallet_id: UUID,
    user: User = Depends(
        require_permission("finance.read")
    ),
    db: Session = Depends(get_db),
):
    wallet = db.get(CustomerWallet, wallet_id)

    if wallet is None:
        raise HTTPException(
            status_code=404,
            detail="Wallet not found.",
        )

    return FinanceWalletRead(
        wallet_id=wallet.id,
        organization_id=wallet.organization_id,
        currency=wallet.currency,
        **wallet_balances(db, wallet),
    )


@router.post(
    "/operator/reservations",
)
def create_reservation(
    payload: FinanceReservationCreate,
    user: User = Depends(
        require_permission("finance.ledger.manage")
    ),
    db: Session = Depends(get_db),
):
    wallet = db.get(CustomerWallet, payload.wallet_id)

    if wallet is None:
        raise HTTPException(
            status_code=404,
            detail="Wallet not found.",
        )

    try:
        reservation = reserve_funds(
            db,
            wallet=wallet,
            amount_minor=payload.amount_minor,
            idempotency_key=payload.idempotency_key,
            reference_type=payload.reference_type,
            reference_id=payload.reference_id,
        )

        db.commit()

        return {
            "reservation_id": str(reservation.id),
            "status": reservation.status,
            "reserved_minor": reservation.reserved_minor,
            "currency": reservation.currency,
        }
    except WalletError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/operator/refunds")
def operator_refund(
    payload: RefundCreate,
    user: User = Depends(
        require_permission("finance.ledger.manage")
    ),
    db: Session = Depends(get_db),
):
    from app.models.finance import CustomerWallet
    from app.services.audit_service import record_audit_event
    from app.services.refund_service import RefundError, queue_refund

    wallet = db.get(CustomerWallet, payload.wallet_id)

    if wallet is None:
        raise HTTPException(
            status_code=404,
            detail="Wallet not found.",
        )

    try:
        refund = queue_refund(
            db,
            wallet=wallet,
            amount_minor=payload.amount_minor,
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
            external_reference=payload.external_reference,
        )

        record_audit_event(
            db,
            actor_user_id=user.id,
            action="finance.refund.queue",
            resource_type="refund",
            resource_id=str(refund.id),
            reason=payload.reason,
            details={
                "amount_minor": payload.amount_minor,
                "currency": refund.currency,
            },
        )

        db.commit()

        return {
            "refund_id": str(refund.id),
            "status": refund.status,
            "amount_minor": refund.amount_minor,
            "currency": refund.currency,
        }

    except RefundError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/operator/adjustments")
def operator_adjustment(
    payload: FinancialAdjustmentCreate,
    user: User = Depends(
        require_permission("finance.ledger.manage")
    ),
    db: Session = Depends(get_db),
):
    from app.models.finance import FinancialAccount
    from app.services.adjustment_service import (
        AdjustmentError,
        create_financial_adjustment,
    )
    from app.services.audit_service import record_audit_event

    debit = db.get(
        FinancialAccount,
        payload.debit_account_id,
    )
    credit = db.get(
        FinancialAccount,
        payload.credit_account_id,
    )

    if debit is None or credit is None:
        raise HTTPException(
            status_code=404,
            detail="Financial account not found.",
        )

    try:
        adjustment = create_financial_adjustment(
            db,
            debit_account=debit,
            credit_account=credit,
            amount_minor=payload.amount_minor,
            adjustment_type=payload.adjustment_type,
            reason=payload.reason,
            actor_user_id=user.id,
            idempotency_key=payload.idempotency_key,
        )

        record_audit_event(
            db,
            actor_user_id=user.id,
            action="finance.adjustment.create",
            resource_type="financial_adjustment",
            resource_id=str(adjustment.id),
            reason=payload.reason,
            details={
                "amount_minor": payload.amount_minor,
                "currency": adjustment.currency,
                "debit_account_id": str(debit.id),
                "credit_account_id": str(credit.id),
            },
        )

        db.commit()

        return {
            "adjustment_id": str(adjustment.id),
            "ledger_transaction_id": str(
                adjustment.ledger_transaction_id
            ),
            "status": "posted",
        }

    except AdjustmentError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/operator/treasury/settlements")
def operator_treasury_settlement(
    payload: TreasurySettlementCreate,
    user: User = Depends(
        require_permission("finance.reconciliation.manage")
    ),
    db: Session = Depends(get_db),
):
    from app.services.audit_service import record_audit_event
    from app.services.treasury_service import (
        TreasuryError,
        settle_gateway_clearing_to_bank,
    )

    try:
        batch = settle_gateway_clearing_to_bank(
            db,
            provider=payload.provider,
            currency=payload.currency,
            amount_minor=payload.amount_minor,
            external_reference=payload.external_reference,
            idempotency_key=payload.idempotency_key,
        )

        record_audit_event(
            db,
            actor_user_id=user.id,
            action="finance.treasury.settle",
            resource_type="treasury_settlement_batch",
            resource_id=str(batch.id),
            details={
                "provider": payload.provider,
                "amount_minor": payload.amount_minor,
                "currency": payload.currency,
            },
        )

        db.commit()

        return {
            "settlement_batch_id": str(batch.id),
            "status": batch.status,
            "amount_minor": batch.amount_minor,
            "currency": batch.currency,
        }

    except TreasuryError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# KF-002F — settlement / reconciliation operator controls
# ---------------------------------------------------------------------------

@router.post("/operator/provider-settlements/fetch")
def operator_provider_settlement_fetch(
    payload: "ProviderSettlementFetchCreate",
    user: User = Depends(
        require_permission("finance.reconciliation.manage")
    ),
    db: Session = Depends(get_db),
):
    from app.models.payment_provider import PaymentProvider
    from app.services.audit_service import record_audit_event
    from app.services.payment_settlement_execution import (
        PaymentSettlementExecutionError,
        enqueue_provider_settlement_fetch,
    )
    from sqlalchemy import select

    provider = db.scalar(
        select(PaymentProvider).where(
            PaymentProvider.code
            == payload.provider_code.strip().lower()
        )
    )

    if provider is None:
        raise HTTPException(
            status_code=404,
            detail="Payment provider not found.",
        )

    try:
        row = enqueue_provider_settlement_fetch(
            db,
            provider=provider,
            cursor=payload.cursor,
            idempotency_key=payload.idempotency_key,
        )

        record_audit_event(
            db,
            actor_user_id=user.id,
            action="finance.settlement.fetch.queue",
            resource_type="payment_financial_outbox",
            resource_id=str(row.id),
            details={
                "provider": provider.code,
                "cursor_present": bool(payload.cursor),
            },
        )

        db.commit()

        return {
            "outbox_id": str(row.id),
            "status": row.status,
            "provider": provider.code,
        }

    except PaymentSettlementExecutionError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/operator/reconciliation/{event_id}/resolve")
def operator_resolve_reconciliation(
    event_id: UUID,
    payload: "ReconciliationResolutionCreate",
    user: User = Depends(
        require_permission("finance.reconciliation.manage")
    ),
    db: Session = Depends(get_db),
):
    from app.models.finance import PaymentReconciliationEvent
    from app.services.audit_service import record_audit_event
    from app.services.payment_reconciliation_service import (
        ReconciliationError,
        resolve_reconciliation_event,
    )

    event = db.get(
        PaymentReconciliationEvent,
        event_id,
    )

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Reconciliation event not found.",
        )

    try:
        previous_outcome = event.outcome

        resolved = resolve_reconciliation_event(
            db,
            event=event,
            correction_reference=payload.correction_reference,
            reason=payload.reason,
        )

        record_audit_event(
            db,
            actor_user_id=user.id,
            action="finance.reconciliation.resolve",
            resource_type="payment_reconciliation_event",
            resource_id=str(resolved.id),
            reason=payload.reason,
            details={
                "provider": resolved.provider,
                "event_id": resolved.event_id,
                "previous_outcome": previous_outcome,
                "outcome": resolved.outcome,
                "correction_reference": payload.correction_reference,
            },
        )

        db.commit()

        return {
            "reconciliation_event_id": str(resolved.id),
            "outcome": resolved.outcome,
            "status": resolved.status,
            "resolution_reason": resolved.resolution_reason,
        }

    except ReconciliationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post("/operator/provider-policy/corridor-check")
def operator_provider_corridor_check(
    payload: "ProviderCorridorCheck",
    user: User = Depends(
        require_permission("finance.payment_providers.manage")
    ),
    db: Session = Depends(get_db),
):
    from app.models.payment_provider import PaymentProvider
    from app.services.audit_service import record_audit_event
    from app.services.payment_provider_policy import (
        PaymentProviderPolicyError,
        enforce_provider_corridor_operation,
    )
    from sqlalchemy import select

    provider = db.scalar(
        select(PaymentProvider).where(
            PaymentProvider.code
            == payload.provider_code.strip().lower()
        )
    )

    if provider is None:
        raise HTTPException(
            status_code=404,
            detail="Payment provider not found.",
        )

    try:
        corridor, transaction, presentment, settlement = (
            enforce_provider_corridor_operation(
                provider,
                source_country_code=payload.source_country_code,
                destination_country_code=payload.destination_country_code,
                transaction_currency=payload.transaction_currency,
                settlement_currency=payload.settlement_currency,
                explicit_fx_transaction_id=(
                    str(payload.explicit_fx_transaction_id)
                    if payload.explicit_fx_transaction_id
                    else None
                ),
                capability=payload.capability,
            )
        )

        record_audit_event(
            db,
            actor_user_id=user.id,
            action="finance.payment_provider.corridor_check",
            resource_type="payment_provider",
            resource_id=str(provider.id),
            details={
                "provider": provider.code,
                "corridor": corridor,
                "transaction_currency": transaction,
                "settlement_currency": settlement,
                "explicit_fx": bool(
                    payload.explicit_fx_transaction_id
                ),
            },
        )

        db.commit()

        return {
            "provider": provider.code,
            "corridor": corridor,
            "transaction_currency": transaction,
            "presentment_currency": presentment,
            "settlement_currency": settlement,
            "allowed": True,
        }

    except PaymentProviderPolicyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
