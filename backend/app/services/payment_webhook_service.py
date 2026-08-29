from __future__ import annotations

import hashlib
import hmac
import os
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment_provider import (
    PaymentProvider,
    PaymentWebhookReceipt,
)
from app.schemas.payment_provider import NormalizedPaymentEvent
from app.services.payment_provider_registry import (
    PaymentAdapterError,
    get_adapter,
)


class PaymentWebhookError(ValueError):
    pass


def resolve_secret_reference(reference: str) -> str:
    reference = reference.strip()

    if not reference:
        raise PaymentWebhookError(
            "Webhook secret reference is not configured."
        )

    if not reference.startswith("env:"):
        raise PaymentWebhookError(
            "Unsupported secret reference scheme."
        )

    env_name = reference[4:].strip()

    if not env_name:
        raise PaymentWebhookError(
            "Webhook environment secret name is empty."
        )

    secret = os.environ.get(env_name, "")

    if not secret:
        raise PaymentWebhookError(
            "Webhook secret is unavailable."
        )

    return secret


def validate_event_timestamp(
    *,
    event_timestamp: int,
    tolerance_seconds: int,
    now: int | None = None,
) -> None:
    current = int(time.time()) if now is None else int(now)

    if abs(current - int(event_timestamp)) > tolerance_seconds:
        raise PaymentWebhookError(
            "Webhook timestamp is outside the accepted replay window."
        )


def verify_and_normalize_webhook(
    *,
    provider: PaymentProvider,
    raw_body: bytes,
    headers: dict[str, str],
    now: int | None = None,
) -> NormalizedPaymentEvent:
    if not provider.enabled:
        raise PaymentWebhookError(
            "Payment provider is disabled."
        )

    try:
        adapter = get_adapter(provider.code)
    except PaymentAdapterError as exc:
        raise PaymentWebhookError(str(exc)) from exc

    secret = resolve_secret_reference(
        provider.webhook_secret_reference
    )

    if not adapter.verify_webhook(
        raw_body=raw_body,
        headers=headers,
        secret=secret,
    ):
        raise PaymentWebhookError(
            "Webhook signature verification failed."
        )

    try:
        event = adapter.normalize_webhook(
            raw_body=raw_body,
            headers=headers,
        )
    except Exception as exc:
        raise PaymentWebhookError(
            "Webhook payload could not be normalized."
        ) from exc

    if event.provider.strip().lower() != provider.code:
        raise PaymentWebhookError(
            "Normalized provider does not match route provider."
        )

    validate_event_timestamp(
        event_timestamp=event.provider_timestamp,
        tolerance_seconds=provider.webhook_tolerance_seconds,
        now=now,
    )

    return event


def canonical_event_hash(
    event: NormalizedPaymentEvent,
) -> str:
    raw = event.model_dump_json(
        exclude_none=False,
    ).encode()

    return hashlib.sha256(raw).hexdigest()


def raw_body_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def get_existing_receipt(
    db: Session,
    *,
    provider: PaymentProvider,
    event_id: str,
) -> PaymentWebhookReceipt | None:
    return db.scalar(
        select(PaymentWebhookReceipt).where(
            PaymentWebhookReceipt.provider_id == provider.id,
            PaymentWebhookReceipt.event_id == event_id,
        )
    )


def assert_receipt_replay_matches(
    *,
    receipt: PaymentWebhookReceipt,
    raw_hash: str,
    normalized_hash: str,
    event_type: str,
) -> None:
    if not hmac.compare_digest(
        receipt.raw_body_sha256,
        raw_hash,
    ):
        raise PaymentWebhookError(
            "Provider event ID replayed with different raw contents."
        )

    if not hmac.compare_digest(
        receipt.normalized_payload_sha256,
        normalized_hash,
    ):
        raise PaymentWebhookError(
            "Provider event ID replayed with different normalized contents."
        )

    if receipt.event_type != event_type:
        raise PaymentWebhookError(
            "Provider event ID replayed with different event type."
        )


def process_provider_webhook(
    db: Session,
    *,
    provider: PaymentProvider,
    raw_body: bytes,
    headers: dict[str, str],
    now: int | None = None,
):
    from app.models.payment_provider import PaymentWebhookReceipt
    from app.services.payment_event_processor import (
        process_normalized_event,
    )

    event = verify_and_normalize_webhook(
        provider=provider,
        raw_body=raw_body,
        headers=headers,
        now=now,
    )

    raw_hash = raw_body_hash(raw_body)
    normalized_hash = canonical_event_hash(event)

    existing = get_existing_receipt(
        db,
        provider=provider,
        event_id=event.event_id,
    )

    if existing is not None:
        assert_receipt_replay_matches(
            receipt=existing,
            raw_hash=raw_hash,
            normalized_hash=normalized_hash,
            event_type=event.event_type,
        )

        return existing, True

    receipt = PaymentWebhookReceipt(
        provider_id=provider.id,
        event_id=event.event_id,
        event_type=event.event_type,
        raw_body_sha256=raw_hash,
        normalized_payload_sha256=normalized_hash,
        provider_timestamp=event.provider_timestamp,
        signature_verified=True,
        processing_status="accepted",
        metadata_json={
            "presentment_currency": event.presentment_currency,
            "settlement_currency": event.settlement_currency,
        },
    )

    db.add(receipt)
    db.flush()

    try:
        resource_type, resource_id = process_normalized_event(
            db,
            event=event,
        )
    except Exception:
        receipt.processing_status = "failed"
        db.flush()
        raise

    receipt.processing_status = "processed"
    receipt.result_resource_type = resource_type
    receipt.result_resource_id = resource_id

    from app.models.finance import PaymentReconciliationEvent

    reconciliation = db.scalar(
        select(PaymentReconciliationEvent).where(
            PaymentReconciliationEvent.provider == event.provider,
            PaymentReconciliationEvent.event_id == event.event_id,
        )
    )

    if reconciliation is not None:
        receipt.reconciliation_event_id = reconciliation.id

    db.flush()

    return receipt, False
