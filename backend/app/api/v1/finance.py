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
