from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class FinancialOutboxError(ValueError):
    pass


@dataclass(frozen=True)
class FinancialOutboxMessage:
    event_type: str
    aggregate_type: str
    aggregate_id: str
    idempotency_key: str
    payload: dict[str, Any]
    payload_hash: str
    available_at: datetime


def canonical_payload_hash(
    payload: dict[str, Any],
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def build_outbox_message(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    idempotency_key: str,
    payload: dict[str, Any],
) -> FinancialOutboxMessage:
    event_type = str(event_type or "").strip()
    aggregate_type = str(
        aggregate_type or ""
    ).strip()
    aggregate_id = str(
        aggregate_id or ""
    ).strip()
    idempotency_key = str(
        idempotency_key or ""
    ).strip()

    if not event_type:
        raise FinancialOutboxError(
            "event_type is required."
        )

    if not aggregate_type:
        raise FinancialOutboxError(
            "aggregate_type is required."
        )

    if not aggregate_id:
        raise FinancialOutboxError(
            "aggregate_id is required."
        )

    if not idempotency_key:
        raise FinancialOutboxError(
            "idempotency_key is required."
        )

    if not isinstance(payload, dict):
        raise FinancialOutboxError(
            "payload must be a dictionary."
        )

    return FinancialOutboxMessage(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        idempotency_key=idempotency_key,
        payload=dict(payload),
        payload_hash=canonical_payload_hash(
            payload
        ),
        available_at=datetime.now(
            timezone.utc
        ),
    )


def enqueue_outbox_message(
    db,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    idempotency_key: str,
    payload: dict[str, Any],
):
    from sqlalchemy import select
    from app.models.payment_reliability import (
        PaymentFinancialOutbox,
    )

    message = build_outbox_message(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        idempotency_key=idempotency_key,
        payload=payload,
    )

    existing = db.scalar(
        select(PaymentFinancialOutbox).where(
            PaymentFinancialOutbox.idempotency_key
            == message.idempotency_key
        )
    )

    if existing is not None:
        if (
            existing.event_type != message.event_type
            or existing.aggregate_type
            != message.aggregate_type
            or existing.aggregate_id
            != message.aggregate_id
            or existing.payload_hash
            != message.payload_hash
        ):
            raise FinancialOutboxError(
                "Outbox idempotency key was reused "
                "with different contents."
            )

        return existing, True

    row = PaymentFinancialOutbox(
        event_type=message.event_type,
        aggregate_type=message.aggregate_type,
        aggregate_id=message.aggregate_id,
        idempotency_key=message.idempotency_key,
        payload_json=message.payload,
        payload_hash=message.payload_hash,
        status="pending",
        attempt_count=0,
        available_at=message.available_at,
    )

    db.add(row)
    db.flush()

    return row, False


def claim_outbox_message(
    db,
    *,
    outbox_id,
):
    from datetime import datetime, timezone
    from app.models.payment_reliability import (
        PaymentFinancialOutbox,
    )

    row = db.get(
        PaymentFinancialOutbox,
        outbox_id,
        with_for_update=True,
    )

    if row is None:
        raise FinancialOutboxError(
            "Outbox message was not found."
        )

    if row.status == "processed":
        return row, True

    if row.status == "processing":
        return row, True

    if row.status not in {
        "pending",
        "failed",
    }:
        raise FinancialOutboxError(
            "Outbox message cannot be claimed "
            f"from status {row.status!r}."
        )

    row.status = "processing"
    row.attempt_count += 1
    row.locked_at = datetime.now(
        timezone.utc
    )
    row.last_error = None

    db.flush()

    return row, False


def mark_outbox_processed(
    db,
    *,
    row,
):
    from datetime import datetime, timezone

    if row.status == "processed":
        return row

    if row.status != "processing":
        raise FinancialOutboxError(
            "Only a processing outbox message "
            "can become processed."
        )

    row.status = "processed"
    row.processed_at = datetime.now(
        timezone.utc
    )
    row.locked_at = None
    row.last_error = None

    db.flush()

    return row


def mark_outbox_failed(
    db,
    *,
    row,
    error: Exception | str,
):
    if row.status == "processed":
        raise FinancialOutboxError(
            "A processed outbox message "
            "cannot be failed."
        )

    if row.status != "processing":
        raise FinancialOutboxError(
            "Only a processing outbox message "
            "can become failed."
        )

    row.status = "failed"
    row.locked_at = None
    row.last_error = str(error)[:2000]

    db.flush()

    return row
