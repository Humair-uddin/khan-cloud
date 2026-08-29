from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import (
    CustomerWallet,
    LedgerEntry,
    LedgerTransaction,
    PaymentDeposit,
    UsageReservation,
)
from app.services.ledger_service import (
    LedgerError,
    LedgerLine,
    account_balance_minor,
    get_or_create_account,
    post_transaction,
    validate_currency,
)


class WalletError(LedgerError):
    pass


def get_or_create_customer_wallet(
    db: Session,
    *,
    organization_id: UUID,
    user_id: UUID | None,
    currency: str,
) -> CustomerWallet:
    currency = validate_currency(currency)

    wallet = db.scalar(
        select(CustomerWallet).where(
            CustomerWallet.organization_id == organization_id,
            CustomerWallet.currency == currency,
        )
    )
    if wallet is not None:
        return wallet

    available = get_or_create_account(
        db,
        account_code=f"customer:{organization_id}:{currency}:available",
        account_type="customer_wallet_available",
        normal_side="credit",
        currency=currency,
        organization_id=organization_id,
        user_id=user_id,
    )

    reserved = get_or_create_account(
        db,
        account_code=f"customer:{organization_id}:{currency}:reserved",
        account_type="customer_wallet_reserved",
        normal_side="credit",
        currency=currency,
        organization_id=organization_id,
        user_id=user_id,
    )

    wallet = CustomerWallet(
        organization_id=organization_id,
        user_id=user_id,
        currency=currency,
        available_account_id=available.id,
        reserved_account_id=reserved.id,
    )
    db.add(wallet)
    db.flush()

    return wallet


def wallet_balances(db: Session, wallet: CustomerWallet) -> dict[str, int]:
    from app.models.finance import FinancialAccount

    available = db.get(
        FinancialAccount,
        wallet.available_account_id,
    )
    reserved = db.get(
        FinancialAccount,
        wallet.reserved_account_id,
    )

    return {
        "available_minor": account_balance_minor(db, available),
        "reserved_minor": account_balance_minor(db, reserved),
    }


def confirm_deposit(
    db: Session,
    *,
    organization_id: UUID,
    user_id: UUID | None,
    currency: str,
    amount_minor: int,
    provider: str,
    provider_event_id: str,
    provider_reference: str = "",
) -> tuple[CustomerWallet, PaymentDeposit]:
    if amount_minor <= 0:
        raise WalletError("Deposit amount must be positive.")

    currency = validate_currency(currency)

    existing = db.scalar(
        select(PaymentDeposit).where(
            PaymentDeposit.provider == provider,
            PaymentDeposit.provider_event_id == provider_event_id,
        )
    )
    if existing is not None:
        if (
            existing.organization_id != organization_id
            or existing.user_id != user_id
            or existing.currency != currency
            or existing.amount_minor != amount_minor
            or existing.provider_reference != provider_reference
        ):
            raise WalletError(
                "Payment provider event ID was reused "
                "with different deposit contents."
            )

        wallet = get_or_create_customer_wallet(
            db,
            organization_id=organization_id,
            user_id=user_id,
            currency=currency,
        )
        return wallet, existing

    wallet = get_or_create_customer_wallet(
        db,
        organization_id=organization_id,
        user_id=user_id,
        currency=currency,
    )

    from app.models.finance import FinancialAccount

    available = db.get(
        FinancialAccount,
        wallet.available_account_id,
    )

    clearing = get_or_create_account(
        db,
        account_code=f"treasury:{provider}:{currency}:clearing",
        account_type="gateway_clearing",
        normal_side="debit",
        currency=currency,
    )

    tx = post_transaction(
        db,
        transaction_type="customer_deposit",
        currency=currency,
        idempotency_key=f"deposit:{provider}:{provider_event_id}",
        external_reference=provider_reference,
        description=f"Customer wallet deposit via {provider}",
        lines=[
            LedgerLine(
                account=clearing,
                side="debit",
                amount_minor=amount_minor,
                memo="Gateway/bank clearing received",
            ),
            LedgerLine(
                account=available,
                side="credit",
                amount_minor=amount_minor,
                memo="Customer wallet liability",
            ),
        ],
    )

    deposit = PaymentDeposit(
        organization_id=organization_id,
        user_id=user_id,
        provider=provider,
        provider_event_id=provider_event_id,
        provider_reference=provider_reference,
        currency=currency,
        amount_minor=amount_minor,
        status="confirmed",
        ledger_transaction_id=tx.id,
    )
    db.add(deposit)
    db.flush()

    return wallet, deposit


def reserve_funds(
    db: Session,
    *,
    wallet: CustomerWallet,
    amount_minor: int,
    idempotency_key: str,
    reference_type: str = "",
    reference_id: str = "",
) -> UsageReservation:
    if amount_minor <= 0:
        raise WalletError("Reservation amount must be positive.")

    preexisting_tx = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.idempotency_key == idempotency_key
        )
    )

    locked_wallet = db.scalar(
        select(CustomerWallet)
        .where(CustomerWallet.id == wallet.id)
        .with_for_update()
    )
    if locked_wallet is None:
        raise WalletError("Customer wallet not found.")
    wallet = locked_wallet

    balances = wallet_balances(db, wallet)

    if balances["available_minor"] < amount_minor:
        raise WalletError("Insufficient available wallet balance.")

    from app.models.finance import FinancialAccount

    available = db.get(
        FinancialAccount,
        wallet.available_account_id,
    )
    reserved = db.get(
        FinancialAccount,
        wallet.reserved_account_id,
    )

    tx = post_transaction(
        db,
        transaction_type="wallet_reservation",
        currency=wallet.currency,
        idempotency_key=idempotency_key,
        lines=[
            LedgerLine(
                account=available,
                side="debit",
                amount_minor=amount_minor,
                memo="Move customer funds out of available",
            ),
            LedgerLine(
                account=reserved,
                side="credit",
                amount_minor=amount_minor,
                memo="Reserve customer funds",
            ),
        ],
        external_reference=reference_id,
    )

    if preexisting_tx is not None:
        existing_reservation = db.scalar(
            select(UsageReservation).where(
                UsageReservation.reserve_transaction_id == tx.id
            )
        )

        if existing_reservation is None:
            raise WalletError(
                "Reservation ledger transaction exists "
                "without its domain reservation record."
            )

        return existing_reservation

    reservation = UsageReservation(
        organization_id=wallet.organization_id,
        user_id=wallet.user_id,
        wallet_id=wallet.id,
        currency=wallet.currency,
        reserved_minor=amount_minor,
        consumed_minor=0,
        released_minor=0,
        status="reserved",
        reference_type=reference_type,
        reference_id=reference_id,
        reserve_transaction_id=tx.id,
    )
    db.add(reservation)
    db.flush()

    return reservation


def release_reservation(
    db: Session,
    *,
    reservation: UsageReservation,
    amount_minor: int,
    idempotency_key: str,
):
    preexisting_tx = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.idempotency_key == idempotency_key
        )
    )

    # A successful release changes released_minor, so retry detection
    # must precede the mutable remaining-balance validation.
    if preexisting_tx is not None:
        replay_entries = db.scalars(
            select(LedgerEntry).where(
                LedgerEntry.transaction_id
                == preexisting_tx.id
            )
        ).all()

        if (
            len(replay_entries) != 2
            or any(
                entry.amount_minor != amount_minor
                for entry in replay_entries
            )
        ):
            raise WalletError(
                "Reservation release idempotency key "
                "was reused with different contents."
            )

        return preexisting_tx

    remaining = (
        reservation.reserved_minor
        - reservation.consumed_minor
        - reservation.released_minor
    )

    if amount_minor <= 0 or amount_minor > remaining:
        raise WalletError("Invalid reservation release amount.")

    wallet = db.get(CustomerWallet, reservation.wallet_id)

    from app.models.finance import FinancialAccount

    available = db.get(
        FinancialAccount,
        wallet.available_account_id,
    )
    reserved = db.get(
        FinancialAccount,
        wallet.reserved_account_id,
    )

    tx = post_transaction(
        db,
        transaction_type="wallet_reservation_release",
        currency=wallet.currency,
        idempotency_key=idempotency_key,
        lines=[
            LedgerLine(
                account=reserved,
                side="debit",
                amount_minor=amount_minor,
            ),
            LedgerLine(
                account=available,
                side="credit",
                amount_minor=amount_minor,
            ),
        ],
    )

    if preexisting_tx is not None:
        return tx

    reservation.released_minor += amount_minor

    if (
        reservation.released_minor + reservation.consumed_minor
        == reservation.reserved_minor
    ):
        reservation.status = "closed"

    db.flush()
    return tx


def extend_reservation(
    db: Session,
    *,
    reservation: UsageReservation,
    amount_minor: int,
    idempotency_key: str,
):
    """Extend an existing usage reservation through the canonical ledger."""
    if amount_minor <= 0:
        raise WalletError("Reservation extension amount must be positive.")

    preexisting_tx = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.idempotency_key == idempotency_key
        )
    )
    if preexisting_tx is not None:
        return preexisting_tx

    wallet = db.scalar(
        select(CustomerWallet)
        .where(CustomerWallet.id == reservation.wallet_id)
        .with_for_update()
    )
    if wallet is None:
        raise WalletError("Reservation wallet not found.")
    balances = wallet_balances(db, wallet)
    if balances["available_minor"] < amount_minor:
        raise WalletError("Insufficient available wallet balance.")

    from app.models.finance import FinancialAccount

    available = db.get(FinancialAccount, wallet.available_account_id)
    reserved = db.get(FinancialAccount, wallet.reserved_account_id)
    tx = post_transaction(
        db,
        transaction_type="wallet_reservation_extension",
        currency=wallet.currency,
        idempotency_key=idempotency_key,
        lines=[
            LedgerLine(
                account=available,
                side="debit",
                amount_minor=amount_minor,
                memo="Extend customer usage reservation",
            ),
            LedgerLine(
                account=reserved,
                side="credit",
                amount_minor=amount_minor,
                memo="Extend reserved customer funds",
            ),
        ],
        external_reference=str(reservation.id),
    )
    reservation.reserved_minor += amount_minor
    reservation.status = "reserved"
    db.flush()
    return tx
