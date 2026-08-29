from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.finance import (
    FinancialAccount,
    LedgerEntry,
    LedgerTransaction,
    SUPPORTED_FINANCE_CURRENCIES,
)


class LedgerError(ValueError):
    pass


@dataclass(frozen=True)
class LedgerLine:
    account: FinancialAccount
    side: str
    amount_minor: int
    memo: str = ""


def validate_currency(currency: str) -> str:
    currency = currency.upper()

    if currency not in SUPPORTED_FINANCE_CURRENCIES:
        raise LedgerError(
            f"Unsupported accounting currency: {currency}"
        )

    return currency


def _request_hash(
    *,
    transaction_type: str,
    currency: str,
    external_reference: str,
    description: str,
    metadata_json: dict,
    reversed_transaction_id: UUID | None,
    lines: list[LedgerLine],
) -> str:
    payload = {
        "transaction_type": transaction_type,
        "currency": currency,
        "external_reference": external_reference,
        "description": description,
        "metadata_json": metadata_json,
        "reversed_transaction_id": (
            str(reversed_transaction_id)
            if reversed_transaction_id is not None
            else None
        ),
        "lines": sorted(
            [
                {
                    "account_id": str(line.account.id),
                    "side": line.side,
                    "amount_minor": line.amount_minor,
                    "memo": line.memo,
                }
                for line in lines
            ],
            key=lambda x: (
                x["account_id"],
                x["side"],
                x["amount_minor"],
                x["memo"],
            ),
        ),
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()

    return hashlib.sha256(canonical).hexdigest()


def get_or_create_account(
    db: Session,
    *,
    account_code: str,
    account_type: str,
    normal_side: str,
    currency: str,
    organization_id: UUID | None = None,
    user_id: UUID | None = None,
    host_node_id: UUID | None = None,
    metadata_json: dict | None = None,
) -> FinancialAccount:
    currency = validate_currency(currency)

    if normal_side not in {"debit", "credit"}:
        raise LedgerError("Invalid account normal side.")

    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.account_code == account_code
        )
    )

    if account is not None:
        if (
            account.currency != currency
            or account.account_type != account_type
            or account.normal_side != normal_side
            or account.organization_id != organization_id
            or account.user_id != user_id
            or account.host_node_id != host_node_id
        ):
            raise LedgerError(
                "Existing financial account conflicts "
                "with requested account identity."
            )

        return account

    account = FinancialAccount(
        account_code=account_code,
        account_type=account_type,
        normal_side=normal_side,
        currency=currency,
        organization_id=organization_id,
        user_id=user_id,
        host_node_id=host_node_id,
        metadata_json=metadata_json or {},
    )

    db.add(account)
    db.flush()

    return account


def post_transaction(
    db: Session,
    *,
    transaction_type: str,
    currency: str,
    idempotency_key: str,
    lines: list[LedgerLine],
    external_reference: str = "",
    description: str = "",
    metadata_json: dict | None = None,
    reversed_transaction_id: UUID | None = None,
) -> LedgerTransaction:
    currency = validate_currency(currency)
    metadata_json = metadata_json or {}

    if not idempotency_key.strip():
        raise LedgerError("Idempotency key is required.")

    if len(lines) < 2:
        raise LedgerError(
            "A ledger transaction requires at least two entries."
        )

    debit_total = 0
    credit_total = 0

    for line in lines:
        if line.account.currency != currency:
            raise LedgerError(
                "Cross-currency entries are forbidden "
                "inside one ledger transaction."
            )

        if line.side not in {"debit", "credit"}:
            raise LedgerError(
                "Ledger side must be debit or credit."
            )

        if line.amount_minor <= 0:
            raise LedgerError(
                "Ledger amount must be positive."
            )

        if line.side == "debit":
            debit_total += line.amount_minor
        else:
            credit_total += line.amount_minor

    if debit_total != credit_total:
        raise LedgerError(
            "Unbalanced transaction: "
            f"debit={debit_total} credit={credit_total}"
        )

    request_hash = _request_hash(
        transaction_type=transaction_type,
        currency=currency,
        external_reference=external_reference,
        description=description,
        metadata_json=metadata_json,
        reversed_transaction_id=reversed_transaction_id,
        lines=lines,
    )

    existing = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.idempotency_key == idempotency_key
        )
    )

    if existing is not None:
        if existing.request_hash != request_hash:
            raise LedgerError(
                "Idempotency key was reused with different "
                "financial transaction contents."
            )

        return existing

    tx = LedgerTransaction(
        transaction_type=transaction_type,
        currency=currency,
        status="posted",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        external_reference=external_reference,
        description=description,
        reversed_transaction_id=reversed_transaction_id,
        posted_at=datetime.now(UTC),
        metadata_json=metadata_json,
    )

    db.add(tx)
    db.flush()

    for line in lines:
        db.add(
            LedgerEntry(
                transaction_id=tx.id,
                account_id=line.account.id,
                side=line.side,
                amount_minor=line.amount_minor,
                memo=line.memo,
            )
        )

    db.flush()

    return tx


def account_balance_minor(
    db: Session,
    account: FinancialAccount,
) -> int:
    debit_expr = func.coalesce(
        func.sum(
            case(
                (
                    LedgerEntry.side == "debit",
                    LedgerEntry.amount_minor,
                ),
                else_=0,
            )
        ),
        0,
    )

    credit_expr = func.coalesce(
        func.sum(
            case(
                (
                    LedgerEntry.side == "credit",
                    LedgerEntry.amount_minor,
                ),
                else_=0,
            )
        ),
        0,
    )

    debit, credit = db.execute(
        select(
            debit_expr,
            credit_expr,
        )
        .join(
            LedgerTransaction,
            LedgerTransaction.id
            == LedgerEntry.transaction_id,
        )
        .where(
            LedgerEntry.account_id == account.id,
            LedgerTransaction.status == "posted",
        )
    ).one()

    debit = int(debit or 0)
    credit = int(credit or 0)

    if account.normal_side == "debit":
        return debit - credit

    return credit - debit


def reverse_transaction(
    db: Session,
    *,
    original_transaction_id: UUID,
    idempotency_key: str,
    reason: str,
) -> LedgerTransaction:
    original = db.get(
        LedgerTransaction,
        original_transaction_id,
    )

    if original is None:
        raise LedgerError(
            "Original transaction not found."
        )

    existing_reversal = db.scalar(
        select(LedgerTransaction).where(
            LedgerTransaction.reversed_transaction_id
            == original.id
        )
    )

    if existing_reversal is not None:
        if existing_reversal.idempotency_key != idempotency_key:
            raise LedgerError(
                "Transaction has already been reversed."
            )

        return existing_reversal

    entries = list(
        db.scalars(
            select(LedgerEntry).where(
                LedgerEntry.transaction_id == original.id
            )
        )
    )

    if not entries:
        raise LedgerError(
            "Original transaction has no ledger entries."
        )

    accounts = {
        account.id: account
        for account in db.scalars(
            select(FinancialAccount).where(
                FinancialAccount.id.in_(
                    [
                        entry.account_id
                        for entry in entries
                    ]
                )
            )
        )
    }

    reversal_lines = [
        LedgerLine(
            account=accounts[entry.account_id],
            side=(
                "credit"
                if entry.side == "debit"
                else "debit"
            ),
            amount_minor=entry.amount_minor,
            memo=f"Reversal: {entry.memo}",
        )
        for entry in entries
    ]

    reversal = post_transaction(
        db,
        transaction_type="reversal",
        currency=original.currency,
        idempotency_key=idempotency_key,
        lines=reversal_lines,
        external_reference=str(original.id),
        description=reason,
        metadata_json={
            "reverses_transaction_id": str(original.id),
        },
        reversed_transaction_id=original.id,
    )

    # Both the original transaction and the reversal are append-only.
    # No UPDATE of either posted ledger transaction is required.
    return reversal
