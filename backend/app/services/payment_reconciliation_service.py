from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.finance import PaymentReconciliationEvent
from app.models.payment_provider import (
    PaymentProvider,
    PaymentProviderReference,
)
from app.models.payment_settlement import (
    PaymentProviderSettlementBatch,
    PaymentProviderSettlementItem,
)


class ReconciliationError(ValueError):
    pass


RECONCILIATION_OUTCOMES = {
    "matched",
    "amount_mismatch",
    "currency_mismatch",
    "missing_internal",
    "missing_provider",
    "duplicate_provider",
    "pending_review",
    "resolved",
}


@dataclass(frozen=True)
class CanonicalEconomicRecord:
    internal_resource_type: str
    internal_resource_id: UUID
    amount_minor: int
    currency: str


def canonical_payload_hash(payload: dict) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    return hashlib.sha256(raw).hexdigest()


def verify_hmac_signature(
    *,
    raw_body: bytes,
    signature_hex: str,
    secret: str,
) -> bool:
    expected = hmac.new(
        secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        expected,
        signature_hex,
    )


def register_provider_event(
    db: Session,
    *,
    provider: str,
    event_id: str,
    payload: dict,
) -> PaymentReconciliationEvent:
    payload_hash = canonical_payload_hash(payload)

    event_hash = hashlib.sha256(
        f"{provider}:{event_id}:{payload_hash}".encode()
    ).hexdigest()

    existing = db.scalar(
        select(PaymentReconciliationEvent).where(
            PaymentReconciliationEvent.provider == provider,
            PaymentReconciliationEvent.event_id == event_id,
        )
    )

    if existing is not None:
        if (
            existing.payload_hash != payload_hash
            or existing.event_hash != event_hash
        ):
            raise ReconciliationError(
                "Provider event ID replayed with different contents."
            )

        return existing

    event = PaymentReconciliationEvent(
        provider=provider,
        event_id=event_id,
        event_hash=event_hash,
        payload_hash=payload_hash,
        status="accepted",
        processed=False,
        reconciliation_type="provider_event",
        outcome="pending_review",
        metadata_json={},
    )

    db.add(event)
    db.flush()

    return event


def mark_event_processed(
    db: Session,
    *,
    event: PaymentReconciliationEvent,
    metadata_json: dict | None = None,
) -> PaymentReconciliationEvent:
    if event.processed:
        return event

    event.processed = True
    event.status = "processed"

    merged = dict(event.metadata_json or {})
    merged.update(metadata_json or {})
    event.metadata_json = merged

    db.flush()

    return event


def _settlement_event_id(
    *,
    batch: PaymentProviderSettlementBatch,
    item: PaymentProviderSettlementItem,
) -> str:
    return (
        f"settlement:{batch.provider_settlement_reference}:"
        f"{item.provider_line_id}"
    )


def reconcile_settlement_item(
    db: Session,
    *,
    provider: PaymentProvider,
    batch: PaymentProviderSettlementBatch,
    item: PaymentProviderSettlementItem,
    expected: CanonicalEconomicRecord | None,
) -> PaymentReconciliationEvent:
    if batch.provider_id != provider.id:
        raise ReconciliationError(
            "Settlement batch does not belong to provider."
        )

    duplicate_count = db.scalar(
        select(func.count())
        .select_from(PaymentProviderSettlementItem)
        .where(
            PaymentProviderSettlementItem.settlement_batch_id
            == batch.id,
            PaymentProviderSettlementItem
            .provider_transaction_reference
            == item.provider_transaction_reference,
        )
    )

    provider_reference = db.scalar(
        select(PaymentProviderReference).where(
            PaymentProviderReference.provider_id
            == provider.id,
            PaymentProviderReference.provider_reference
            == item.provider_transaction_reference,
        )
    )

    if duplicate_count and duplicate_count > 1:
        outcome = "duplicate_provider"
    elif expected is None:
        outcome = "missing_internal"
    elif provider_reference is None:
        # The economic expectation may have been supplied by an
        # explicit reconciliation scan even though no provider
        # identity mapping exists.
        outcome = "pending_review"
    elif (
        expected.currency.strip().upper()
        != item.presentment_currency
    ):
        outcome = "currency_mismatch"
    elif (
        expected.amount_minor
        != item.gross_amount_minor
    ):
        outcome = "amount_mismatch"
    else:
        outcome = "matched"

    payload = {
        "provider_id": str(provider.id),
        "provider_code": provider.code,
        "settlement_batch_id": str(batch.id),
        "settlement_item_id": str(item.id),
        "provider_transaction_reference": (
            item.provider_transaction_reference
        ),
        "provider_amount_minor": (
            item.gross_amount_minor
        ),
        "provider_currency": (
            item.presentment_currency
        ),
        "internal_resource_type": (
            expected.internal_resource_type
            if expected
            else ""
        ),
        "internal_resource_id": (
            str(expected.internal_resource_id)
            if expected
            else ""
        ),
        "internal_amount_minor": (
            expected.amount_minor
            if expected
            else None
        ),
        "internal_currency": (
            expected.currency.upper()
            if expected
            else ""
        ),
        "outcome": outcome,
    }

    event = register_provider_event(
        db,
        provider=provider.code,
        event_id=_settlement_event_id(
            batch=batch,
            item=item,
        ),
        payload=payload,
    )

    event.reconciliation_type = "provider_settlement"
    event.outcome = outcome
    event.provider_amount_minor = (
        item.gross_amount_minor
    )
    event.internal_amount_minor = (
        expected.amount_minor
        if expected
        else None
    )
    event.provider_currency = (
        item.presentment_currency
    )
    event.internal_currency = (
        expected.currency.upper()
        if expected
        else ""
    )
    event.internal_resource_type = (
        expected.internal_resource_type
        if expected
        else ""
    )
    event.internal_resource_id = (
        expected.internal_resource_id
        if expected
        else None
    )
    event.status = (
        "processed"
        if outcome == "matched"
        else "review_required"
    )
    event.processed = outcome == "matched"

    item.reconciliation_status = outcome
    item.reconciliation_event_id = event.id

    if expected is not None:
        item.internal_resource_type = (
            expected.internal_resource_type
        )
        item.internal_resource_id = (
            expected.internal_resource_id
        )

    db.flush()

    return event


def register_missing_provider(
    db: Session,
    *,
    provider: PaymentProvider,
    expected: CanonicalEconomicRecord,
    event_id: str,
) -> PaymentReconciliationEvent:
    payload = {
        "provider_id": str(provider.id),
        "internal_resource_type": (
            expected.internal_resource_type
        ),
        "internal_resource_id": str(
            expected.internal_resource_id
        ),
        "internal_amount_minor": expected.amount_minor,
        "internal_currency": expected.currency.upper(),
        "outcome": "missing_provider",
    }

    event = register_provider_event(
        db,
        provider=provider.code,
        event_id=event_id,
        payload=payload,
    )

    event.reconciliation_type = "provider_settlement"
    event.outcome = "missing_provider"
    event.status = "review_required"
    event.processed = False
    event.internal_resource_type = (
        expected.internal_resource_type
    )
    event.internal_resource_id = (
        expected.internal_resource_id
    )
    event.internal_amount_minor = (
        expected.amount_minor
    )
    event.internal_currency = (
        expected.currency.upper()
    )

    db.flush()

    return event


def resolve_reconciliation_event(
    db: Session,
    *,
    event: PaymentReconciliationEvent,
    reason: str,
    correction_reference: str,
) -> PaymentReconciliationEvent:
    reason = str(reason or "").strip()
    correction_reference = str(
        correction_reference or ""
    ).strip()

    if not reason:
        raise ReconciliationError(
            "Reconciliation resolution reason is required."
        )

    if not correction_reference:
        raise ReconciliationError(
            "Adjustment/reversal reference is required "
            "to resolve reconciliation."
        )

    if event.outcome == "resolved":
        return event

    if event.outcome == "matched":
        raise ReconciliationError(
            "A matched reconciliation does not require resolution."
        )

    event.outcome = "resolved"
    event.status = "resolved"
    event.processed = True
    event.resolution_reason = reason
    event.resolved_at = datetime.now(
        timezone.utc
    )

    metadata = dict(
        event.metadata_json or {}
    )
    metadata["correction_reference"] = (
        correction_reference
    )
    event.metadata_json = metadata

    db.flush()

    return event
