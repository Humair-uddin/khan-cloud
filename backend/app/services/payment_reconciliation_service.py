from __future__ import annotations

import hashlib
import hmac
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import PaymentReconciliationEvent


class ReconciliationError(ValueError):
    pass


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
