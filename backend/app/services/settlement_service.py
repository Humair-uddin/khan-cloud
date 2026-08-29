from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import (
    CustomerWallet,
    FinancialAccount,
    HostEarning,
    LedgerTransaction,
    LedgerTransaction,
    HostSettlementAccount,
    UsageReservation,
)
from app.services.ledger_service import (
    LedgerLine,
    get_or_create_account,
    post_transaction,
    validate_currency,
)


class SettlementError(ValueError):
    pass


def get_or_create_host_settlement(
    db: Session,
    *,
    host_node_id: UUID,
    currency: str,
) -> HostSettlementAccount:
    currency = validate_currency(currency)

    settlement = db.scalar(
        select(HostSettlementAccount).where(
            HostSettlementAccount.host_node_id == host_node_id,
            HostSettlementAccount.currency == currency,
        )
    )
    if settlement is not None:
        return settlement

    pending = get_or_create_account(
        db,
        account_code=f"host:{host_node_id}:{currency}:pending",
        account_type="host_payable_pending",
        normal_side="credit",
        currency=currency,
        host_node_id=host_node_id,
    )

    held = get_or_create_account(
        db,
        account_code=f"host:{host_node_id}:{currency}:held",
        account_type="host_payable_held",
        normal_side="credit",
        currency=currency,
        host_node_id=host_node_id,
    )

    available = get_or_create_account(
        db,
        account_code=f"host:{host_node_id}:{currency}:available",
        account_type="host_payable_available",
        normal_side="credit",
        currency=currency,
        host_node_id=host_node_id,
    )

    settlement = HostSettlementAccount(
        host_node_id=host_node_id,
        currency=currency,
        pending_account_id=pending.id,
        held_account_id=held.id,
        available_account_id=available.id,
    )
    db.add(settlement)
    db.flush()

    return settlement


def consume_reserved_usage(
    db: Session,
    *,
    reservation: UsageReservation,
    host_node_id: UUID,
    gross_charge_minor: int,
    host_amount_minor: int,
    idempotency_key: str,
) -> HostEarning:
    if gross_charge_minor <= 0:
        raise SettlementError("Gross usage charge must be positive.")

    preexisting_tx = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.idempotency_key == idempotency_key
        )
    )

    # Replay recognition must happen before checking the reservation's
    # mutable remaining balance. A successful first call has already
    # consumed funds, so applying the remaining-funds gate first would
    # incorrectly reject the legitimate retry.
    if preexisting_tx is not None:
        existing_earning = db.scalar(
            select(HostEarning).where(
                HostEarning.earning_transaction_id
                == preexisting_tx.id
            )
        )

        if existing_earning is None:
            raise SettlementError(
                "Usage ledger transaction exists without "
                "its HostEarning domain record."
            )

        expected_platform_minor = (
            gross_charge_minor - host_amount_minor
        )

        if (
            existing_earning.host_node_id != host_node_id
            or existing_earning.host_amount_minor
            != host_amount_minor
            or existing_earning.platform_revenue_minor
            != expected_platform_minor
        ):
            raise SettlementError(
                "Usage idempotency key was reused "
                "with different usage contents."
            )

        return existing_earning

    if host_amount_minor < 0 or host_amount_minor > gross_charge_minor:
        raise SettlementError("Invalid host payout allocation.")

    remaining = (
        reservation.reserved_minor
        - reservation.consumed_minor
        - reservation.released_minor
    )

    if gross_charge_minor > remaining:
        raise SettlementError("Usage charge exceeds reserved funds.")

    platform_revenue_minor = gross_charge_minor - host_amount_minor

    wallet = db.get(CustomerWallet, reservation.wallet_id)

    settlement = get_or_create_host_settlement(
        db,
        host_node_id=host_node_id,
        currency=reservation.currency,
    )

    customer_reserved = db.get(
        FinancialAccount,
        wallet.reserved_account_id,
    )
    host_pending = db.get(
        FinancialAccount,
        settlement.pending_account_id,
    )

    revenue = get_or_create_account(
        db,
        account_code=f"khan:{reservation.currency}:platform-revenue",
        account_type="platform_revenue",
        normal_side="credit",
        currency=reservation.currency,
    )

    lines = [
        LedgerLine(
            account=customer_reserved,
            side="debit",
            amount_minor=gross_charge_minor,
            memo="Customer usage consumption",
        ),
    ]

    if host_amount_minor:
        lines.append(
            LedgerLine(
                account=host_pending,
                side="credit",
                amount_minor=host_amount_minor,
                memo="Host earning pending review",
            )
        )

    if platform_revenue_minor:
        lines.append(
            LedgerLine(
                account=revenue,
                side="credit",
                amount_minor=platform_revenue_minor,
                memo="Khan Cloud platform revenue",
            )
        )

    tx = post_transaction(
        db,
        transaction_type="usage_charge",
        currency=reservation.currency,
        idempotency_key=idempotency_key,
        lines=lines,
        external_reference=str(reservation.id),
    )

    if preexisting_tx is not None:
        existing_earning = db.scalar(
            select(HostEarning).where(
                HostEarning.earning_transaction_id == tx.id
            )
        )

        if existing_earning is None:
            raise SettlementError(
                "Usage ledger transaction exists "
                "without its HostEarning domain record."
            )

        return existing_earning

    earning = HostEarning(
        host_node_id=host_node_id,
        usage_reservation_id=reservation.id,
        currency=reservation.currency,
        gross_charge_minor=gross_charge_minor,
        host_amount_minor=host_amount_minor,
        platform_revenue_minor=platform_revenue_minor,
        status="pending",
        earning_transaction_id=tx.id,
    )

    reservation.consumed_minor += gross_charge_minor

    if (
        reservation.consumed_minor + reservation.released_minor
        == reservation.reserved_minor
    ):
        reservation.status = "closed"

    db.add(earning)
    db.flush()

    return earning


def move_earning_to_held(
    db: Session,
    *,
    earning: HostEarning,
    idempotency_key: str,
):
    if earning.status != "pending":
        raise SettlementError("Only pending earnings can be held.")

    settlement = get_or_create_host_settlement(
        db,
        host_node_id=earning.host_node_id,
        currency=earning.currency,
    )

    pending = db.get(
        FinancialAccount,
        settlement.pending_account_id,
    )
    held = db.get(
        FinancialAccount,
        settlement.held_account_id,
    )

    tx = post_transaction(
        db,
        transaction_type="host_earning_hold",
        currency=earning.currency,
        idempotency_key=idempotency_key,
        lines=[
            LedgerLine(
                account=pending,
                side="debit",
                amount_minor=earning.host_amount_minor,
            ),
            LedgerLine(
                account=held,
                side="credit",
                amount_minor=earning.host_amount_minor,
            ),
        ],
    )

    earning.status = "held"
    db.flush()
    return tx


def release_earning_available(
    db: Session,
    *,
    earning: HostEarning,
    idempotency_key: str,
):
    if earning.status not in {"pending", "held"}:
        raise SettlementError(
            "Only pending or held earnings can become available."
        )

    settlement = get_or_create_host_settlement(
        db,
        host_node_id=earning.host_node_id,
        currency=earning.currency,
    )

    source_id = (
        settlement.held_account_id
        if earning.status == "held"
        else settlement.pending_account_id
    )

    source = db.get(FinancialAccount, source_id)
    available = db.get(
        FinancialAccount,
        settlement.available_account_id,
    )

    tx = post_transaction(
        db,
        transaction_type="host_earning_available",
        currency=earning.currency,
        idempotency_key=idempotency_key,
        lines=[
            LedgerLine(
                account=source,
                side="debit",
                amount_minor=earning.host_amount_minor,
            ),
            LedgerLine(
                account=available,
                side="credit",
                amount_minor=earning.host_amount_minor,
            ),
        ],
    )

    earning.status = "available"
    db.flush()
    return tx


def consume_reserved_platform_usage(
    db: Session,
    *,
    reservation: UsageReservation,
    gross_charge_minor: int,
    idempotency_key: str,
):
    """Consume Khan-owned usage directly to platform revenue.

    Unlike marketplace usage, Khan-owned capacity must not create a synthetic
    HostEarning payable back to Khan Cloud itself.
    """
    if gross_charge_minor <= 0:
        raise SettlementError("Gross usage charge must be positive.")

    preexisting_tx = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.idempotency_key == idempotency_key
        )
    )
    if preexisting_tx is not None:
        return preexisting_tx

    remaining = (
        reservation.reserved_minor
        - reservation.consumed_minor
        - reservation.released_minor
    )
    if gross_charge_minor > remaining:
        raise SettlementError("Usage charge exceeds reserved funds.")

    wallet = db.get(CustomerWallet, reservation.wallet_id)
    customer_reserved = db.get(
        FinancialAccount,
        wallet.reserved_account_id,
    )
    revenue = get_or_create_account(
        db,
        account_code=f"khan:{reservation.currency}:platform-revenue",
        account_type="platform_revenue",
        normal_side="credit",
        currency=reservation.currency,
    )
    tx = post_transaction(
        db,
        transaction_type="usage_charge",
        currency=reservation.currency,
        idempotency_key=idempotency_key,
        lines=[
            LedgerLine(
                account=customer_reserved,
                side="debit",
                amount_minor=gross_charge_minor,
                memo="Customer gaming usage consumption",
            ),
            LedgerLine(
                account=revenue,
                side="credit",
                amount_minor=gross_charge_minor,
                memo="Khan Cloud gaming platform revenue",
            ),
        ],
        external_reference=str(reservation.id),
    )
    reservation.consumed_minor += gross_charge_minor
    if (
        reservation.consumed_minor + reservation.released_minor
        == reservation.reserved_minor
    ):
        reservation.status = "closed"
    db.flush()
    return tx
