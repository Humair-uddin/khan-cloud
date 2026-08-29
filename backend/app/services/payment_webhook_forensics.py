from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class WebhookForensicError(ValueError):
    pass


def canonical_json_hash(
    payload: Any,
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ForensicWebhookRecord:
    provider_code: str
    event_id: str
    payload_hash: str
    signature_fingerprint: str | None
    outcome_code: str
    http_status: int
    retryable: bool
    error_class: str | None
    error_message: str | None
    received_at: datetime


def signature_fingerprint(
    signature: str | None,
) -> str | None:
    if not signature:
        return None

    return hashlib.sha256(
        signature.encode("utf-8")
    ).hexdigest()


def build_forensic_record(
    *,
    provider_code: str,
    event_id: str,
    payload: Any,
    signature: str | None,
    outcome_code: str,
    http_status: int,
    retryable: bool,
    error: Exception | None = None,
) -> ForensicWebhookRecord:
    provider_code = str(
        provider_code or ""
    ).strip()

    event_id = str(
        event_id or ""
    ).strip()

    if not provider_code:
        raise WebhookForensicError(
            "provider_code is required."
        )

    if not event_id:
        raise WebhookForensicError(
            "event_id is required."
        )

    return ForensicWebhookRecord(
        provider_code=provider_code,
        event_id=event_id,
        payload_hash=canonical_json_hash(
            payload
        ),
        signature_fingerprint=signature_fingerprint(
            signature
        ),
        outcome_code=str(outcome_code),
        http_status=int(http_status),
        retryable=bool(retryable),
        error_class=(
            type(error).__name__
            if error
            else None
        ),
        error_message=(
            str(error)[:1000]
            if error
            else None
        ),
        received_at=datetime.now(
            timezone.utc
        ),
    )


def persist_forensic_record(
    db,
    *,
    record: ForensicWebhookRecord,
):
    from app.models.payment_reliability import (
        PaymentWebhookForensicEvent,
    )

    row = PaymentWebhookForensicEvent(
        provider_code=record.provider_code,
        event_id=record.event_id,
        payload_hash=record.payload_hash,
        signature_fingerprint=(
            record.signature_fingerprint
        ),
        outcome_code=record.outcome_code,
        http_status=record.http_status,
        retryable=record.retryable,
        error_class=record.error_class,
        error_message=record.error_message,
        received_at=record.received_at,
    )

    db.add(row)
    db.flush()

    return row


def persist_forensic_record_independent(
    *,
    record: ForensicWebhookRecord,
):
    #
    # Deliberately independent transaction:
    # finance/webhook transaction may be rolled back while forensic
    # evidence must survive.
    #
    from app.db.database import SessionLocal

    forensic_db = SessionLocal()

    try:
        row = persist_forensic_record(
            forensic_db,
            record=record,
        )
        forensic_db.commit()
        forensic_db.refresh(row)
        return row
    except Exception:
        forensic_db.rollback()
        raise
    finally:
        forensic_db.close()
