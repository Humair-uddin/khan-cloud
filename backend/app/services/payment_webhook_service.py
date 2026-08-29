from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment_provider import (
    PaymentProvider,
    PaymentWebhookReceipt,
)
from app.schemas.payment_provider import (
    NormalizedPaymentEvent,
)
from app.services.payment_adapter_registry import (
    PaymentAdapterError as ImplementationAdapterError,
    create_adapter_for_provider,
)
from app.services.payment_provider_policy import (
    PaymentProviderPolicyError,
    ProviderOperationPolicy,
    enforce_provider_operation,
)
from app.services.payment_provider_registry import (
    PaymentAdapterError as LegacyAdapterError,
    get_adapter as get_legacy_adapter,
)
from app.services.payment_secret_resolver import (
    PaymentSecretError,
    resolve_secret,
)


class PaymentWebhookError(ValueError):
    pass


_CAPABILITY_BY_EVENT = {
    "deposit.succeeded": "deposits",
    "refund.processing": "refunds",
    "refund.succeeded": "refunds",
    "refund.failed": "refunds",
    "chargeback.created": "chargebacks",
    "payout.processing": "payouts",
    "payout.paid": "payouts",
    "payout.failed": "payouts",
    "treasury.settled": "treasury_settlement",
}


def resolve_secret_reference(
    reference: str,
) -> str:
    try:
        return resolve_secret(reference)
    except PaymentSecretError as exc:
        raise PaymentWebhookError(
            str(exc)
        ) from exc


def validate_event_timestamp(
    *,
    event_timestamp: int,
    tolerance_seconds: int,
    now: int | None = None,
) -> None:
    current = (
        int(time.time())
        if now is None
        else int(now)
    )

    if (
        abs(current - int(event_timestamp))
        > tolerance_seconds
    ):
        raise PaymentWebhookError(
            "Webhook timestamp is outside "
            "the accepted replay window."
        )


def _adapter_for_provider(
    provider: PaymentProvider,
):
    #
    # KF-002D architecture:
    #   provider.code       = merchant/account instance
    #   provider.adapter_type = reusable implementation
    #
    # During transition, legacy test adapters remain supported only
    # when adapter_type == provider.code. Real multi-account provider
    # configurations use the adapter_type registry.
    #
    try:
        return create_adapter_for_provider(
            provider
        )
    except ImplementationAdapterError as primary:
        if (
            provider.adapter_type.strip().lower()
            != provider.code.strip().lower()
        ):
            raise PaymentWebhookError(
                str(primary)
            ) from primary

        try:
            return get_legacy_adapter(
                provider.code
            )
        except LegacyAdapterError as legacy:
            raise PaymentWebhookError(
                str(primary)
            ) from legacy


def _event_policy(
    *,
    provider: PaymentProvider,
    event: NormalizedPaymentEvent,
) -> None:
    capability = _CAPABILITY_BY_EVENT.get(
        event.event_type
    )

    if capability is None:
        raise PaymentWebhookError(
            "Unsupported normalized event type."
        )

    transaction_currency = (
        event.currency
        or event.presentment_currency
        or event.settlement_currency
    )

    try:
        enforce_provider_operation(
            provider,
            ProviderOperationPolicy(
                capability=capability,
                currency=transaction_currency,
                presentment_currency=(
                    event.presentment_currency
                ),
                settlement_currency=(
                    event.settlement_currency
                ),
                #
                # A webhook cannot silently declare that FX happened.
                # Explicit FX remains a separate canonical KF-001
                # financial transaction.
                #
                allow_explicit_fx=False,
            ),
        )
    except PaymentProviderPolicyError as exc:
        raise PaymentWebhookError(
            str(exc)
        ) from exc


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

    adapter = _adapter_for_provider(
        provider
    )

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

    if (
        event.provider.strip().lower()
        != provider.code.strip().lower()
    ):
        raise PaymentWebhookError(
            "Normalized provider does not match "
            "route provider."
        )

    validate_event_timestamp(
        event_timestamp=event.provider_timestamp,
        tolerance_seconds=(
            provider.webhook_tolerance_seconds
        ),
        now=now,
    )

    _event_policy(
        provider=provider,
        event=event,
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
    return hashlib.sha256(
        raw_body
    ).hexdigest()


def get_existing_receipt(
    db: Session,
    *,
    provider: PaymentProvider,
    event_id: str,
) -> PaymentWebhookReceipt | None:
    return db.scalar(
        select(PaymentWebhookReceipt).where(
            PaymentWebhookReceipt.provider_id
            == provider.id,
            PaymentWebhookReceipt.event_id
            == event_id,
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
            "Provider event ID replayed "
            "with different raw contents."
        )

    if not hmac.compare_digest(
        receipt.normalized_payload_sha256,
        normalized_hash,
    ):
        raise PaymentWebhookError(
            "Provider event ID replayed with "
            "different normalized contents."
        )

    if receipt.event_type != event_type:
        raise PaymentWebhookError(
            "Provider event ID replayed "
            "with different event type."
        )


def process_provider_webhook(
    db: Session,
    *,
    provider: PaymentProvider,
    raw_body: bytes,
    headers: dict[str, str],
    now: int | None = None,
):
    from app.services.payment_event_processor import (
        process_normalized_event,
    )

    event = verify_and_normalize_webhook(
        provider=provider,
        raw_body=raw_body,
        headers=headers,
        now=now,
    )

    raw_hash = raw_body_hash(
        raw_body
    )
    normalized_hash = canonical_event_hash(
        event
    )

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
        normalized_payload_sha256=(
            normalized_hash
        ),
        provider_timestamp=(
            event.provider_timestamp
        ),
        signature_verified=True,
        processing_status="accepted",
        metadata_json={
            "presentment_currency": (
                event.presentment_currency
            ),
            "settlement_currency": (
                event.settlement_currency
            ),
        },
    )

    db.add(receipt)
    db.flush()

    resource_type, resource_id = (
        process_normalized_event(
            db,
            event=event,
        )
    )

    receipt.processing_status = "processed"
    receipt.result_resource_type = resource_type
    receipt.result_resource_id = resource_id

    from app.models.finance import (
        PaymentReconciliationEvent,
    )

    reconciliation = db.scalar(
        select(
            PaymentReconciliationEvent
        ).where(
            PaymentReconciliationEvent.provider
            == event.provider,
            PaymentReconciliationEvent.event_id
            == event.event_id,
        )
    )

    if reconciliation is not None:
        receipt.reconciliation_event_id = (
            reconciliation.id
        )

    db.flush()

    return receipt, False
