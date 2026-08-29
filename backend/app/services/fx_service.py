from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import FxConversion
from app.services.ledger_service import (
    LedgerError,
    LedgerLine,
    get_or_create_account,
    post_transaction,
    validate_currency,
)


class FxError(ValueError):
    pass


def post_explicit_fx_conversion(
    db: Session,
    *,
    source_currency: str,
    target_currency: str,
    source_amount_minor: int,
    target_amount_minor: int,
    rate_numerator: int,
    rate_denominator: int,
    rate_source: str,
    source_debit_account,
    target_credit_account,
    idempotency_key: str,
) -> FxConversion:
    source_currency = validate_currency(source_currency)
    target_currency = validate_currency(target_currency)

    if source_currency == target_currency:
        raise FxError(
            "FX conversion requires two different currencies."
        )

    if min(
        source_amount_minor,
        target_amount_minor,
        rate_numerator,
        rate_denominator,
    ) <= 0:
        raise FxError(
            "FX amounts and rates must be positive."
        )

    if not rate_source.strip():
        raise FxError(
            "FX rate source is required."
        )

    if source_debit_account.currency != source_currency:
        raise FxError(
            "FX source account currency mismatch."
        )

    if target_credit_account.currency != target_currency:
        raise FxError(
            "FX target account currency mismatch."
        )

    source_bridge = get_or_create_account(
        db,
        account_code=f"fx:{source_currency}:bridge",
        account_type="fx_bridge",
        normal_side="credit",
        currency=source_currency,
    )

    target_bridge = get_or_create_account(
        db,
        account_code=f"fx:{target_currency}:bridge",
        account_type="fx_bridge",
        normal_side="debit",
        currency=target_currency,
    )

    # Bind every economically material FX term into both ledger
    # request hashes. A retry that changes the amount/rate/source
    # is therefore rejected even though the idempotency key matches.
    fx_metadata = {
        "fx_idempotency_key": idempotency_key,
        "source_currency": source_currency,
        "target_currency": target_currency,
        "source_amount_minor": source_amount_minor,
        "target_amount_minor": target_amount_minor,
        "rate_numerator": rate_numerator,
        "rate_denominator": rate_denominator,
        "rate_source": rate_source,
    }

    try:
        # A SAVEPOINT prevents a caller that catches FxError from
        # accidentally committing only one leg of the conversion.
        with db.begin_nested():
            source_tx = post_transaction(
                db,
                transaction_type="fx_source",
                currency=source_currency,
                idempotency_key=f"{idempotency_key}:source",
                lines=[
                    LedgerLine(
                        account=source_debit_account,
                        side="debit",
                        amount_minor=source_amount_minor,
                    ),
                    LedgerLine(
                        account=source_bridge,
                        side="credit",
                        amount_minor=source_amount_minor,
                    ),
                ],
                metadata_json=fx_metadata,
            )

            target_tx = post_transaction(
                db,
                transaction_type="fx_target",
                currency=target_currency,
                idempotency_key=f"{idempotency_key}:target",
                lines=[
                    LedgerLine(
                        account=target_bridge,
                        side="debit",
                        amount_minor=target_amount_minor,
                    ),
                    LedgerLine(
                        account=target_credit_account,
                        side="credit",
                        amount_minor=target_amount_minor,
                    ),
                ],
                metadata_json=fx_metadata,
            )

            existing = db.scalar(
                select(FxConversion).where(
                    FxConversion.source_transaction_id
                    == source_tx.id
                )
            )

            if existing is not None:
                if (
                    existing.target_transaction_id != target_tx.id
                    or existing.source_currency != source_currency
                    or existing.target_currency != target_currency
                    or existing.source_amount_minor
                    != source_amount_minor
                    or existing.target_amount_minor
                    != target_amount_minor
                    or existing.rate_numerator != rate_numerator
                    or existing.rate_denominator != rate_denominator
                    or existing.rate_source != rate_source
                ):
                    raise FxError(
                        "FX idempotency key was reused "
                        "with different conversion contents."
                    )

                return existing

            conversion = FxConversion(
                source_currency=source_currency,
                target_currency=target_currency,
                source_amount_minor=source_amount_minor,
                target_amount_minor=target_amount_minor,
                rate_numerator=rate_numerator,
                rate_denominator=rate_denominator,
                rate_source=rate_source,
                source_transaction_id=source_tx.id,
                target_transaction_id=target_tx.id,
                status="posted",
            )

            db.add(conversion)
            db.flush()

            return conversion

    except LedgerError as exc:
        raise FxError(str(exc)) from exc
