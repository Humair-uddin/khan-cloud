from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import (
    CustomerWallet,
    Payout,
    Refund,
)
from app.models.payment_provider import PaymentProvider
from app.schemas.payment_provider import NormalizedPaymentEvent
from app.services.audit_service import record_audit_event
from app.services.payment_provider_reference_service import (
    bind_provider_reference,
)
from app.services.payment_reconciliation_service import (
    mark_event_processed,
    register_provider_event,
)
from app.services.payout_service import (
    mark_payout_failed,
    mark_payout_paid,
    mark_payout_processing,
)
from app.services.refund_service import (
    mark_refund_failed,
    mark_refund_paid,
    mark_refund_processing,
    post_chargeback,
)
from app.services.treasury_service import (
    settle_gateway_clearing_to_bank,
)
from app.services.wallet_service import confirm_deposit


class PaymentEventProcessingError(ValueError):
    pass


def _required(value, field: str):
    if value is None:
        raise PaymentEventProcessingError(
            f"{field} is required for this payment event."
        )
    return value


def _wallet(
    db: Session,
    wallet_id: UUID | None,
) -> CustomerWallet:
    wallet = db.get(
        CustomerWallet,
        _required(wallet_id, "wallet_id"),
    )

    if wallet is None:
        raise PaymentEventProcessingError(
            "Customer wallet was not found."
        )

    return wallet


def _provider(
    db: Session,
    code: str,
) -> PaymentProvider:
    provider = db.scalar(
        select(PaymentProvider).where(
            PaymentProvider.code
            == code.strip().lower()
        )
    )

    if provider is None:
        raise PaymentEventProcessingError(
            "Payment provider configuration "
            "was not found."
        )

    return provider


def _validate_resource_amount(
    *,
    event: NormalizedPaymentEvent,
    amount_minor: int,
    currency: str,
) -> None:
    if (
        event.amount_minor is not None
        and event.amount_minor != amount_minor
    ):
        raise PaymentEventProcessingError(
            "Provider callback amount does not "
            "match the internal financial resource."
        )

    if (
        event.currency is not None
        and event.currency != currency
    ):
        raise PaymentEventProcessingError(
            "Provider callback currency does not "
            "match the internal financial resource."
        )


def _bind_reference(
    db: Session,
    *,
    provider: PaymentProvider,
    reference_type: str,
    provider_reference: str,
    resource_type: str,
    resource_id: UUID,
    event: NormalizedPaymentEvent,
) -> None:
    if not provider_reference.strip():
        return

    bind_provider_reference(
        db,
        provider=provider,
        reference_type=reference_type,
        provider_reference=provider_reference,
        internal_resource_type=resource_type,
        internal_resource_id=resource_id,
        # External provider references identify the economic
        # resource across multiple lifecycle callbacks. Event identity
        # belongs to PaymentReconciliationEvent/WebhookReceipt instead;
        # storing event_id/event_type here would make a legitimate
        # processing -> paid callback look like a reference conflict.
        metadata_json={
            "provider": event.provider,
        },
    )


def process_normalized_event(
    db: Session,
    *,
    event: NormalizedPaymentEvent,
) -> tuple[str, UUID | None]:
    payload = event.model_dump(
        mode="json",
        exclude_none=False,
    )

    reconciliation = register_provider_event(
        db,
        provider=event.provider,
        event_id=event.event_id,
        payload=payload,
    )

    if reconciliation.processed:
        metadata = reconciliation.metadata_json or {}
        resource_id = metadata.get("resource_id")

        return (
            metadata.get("resource_type", ""),
            UUID(resource_id)
            if resource_id
            else None,
        )

    provider = _provider(
        db,
        event.provider,
    )

    resource_type = ""
    resource_id = None
    audit_action = ""

    if event.event_type == "deposit.succeeded":
        organization_id = _required(
            event.organization_id,
            "organization_id",
        )
        amount = _required(
            event.amount_minor,
            "amount_minor",
        )
        currency = _required(
            event.currency,
            "currency",
        )

        if not event.provider_reference:
            raise PaymentEventProcessingError(
                "provider_reference is required "
                "for deposits."
            )

        _, deposit = confirm_deposit(
            db,
            organization_id=organization_id,
            user_id=event.user_id,
            currency=currency,
            amount_minor=amount,
            provider=event.provider,
            provider_event_id=event.event_id,
            provider_reference=event.provider_reference,
        )

        resource_type = "payment_deposit"
        resource_id = deposit.id
        audit_action = "finance.deposit.provider_confirm"

        _bind_reference(
            db,
            provider=provider,
            reference_type="deposit",
            provider_reference=(
                event.provider_reference
            ),
            resource_type=resource_type,
            resource_id=resource_id,
            event=event,
        )

    elif event.event_type == "chargeback.created":
        wallet = _wallet(
            db,
            event.wallet_id,
        )

        if not event.dispute_id:
            raise PaymentEventProcessingError(
                "dispute_id is required for chargebacks."
            )

        dispute = post_chargeback(
            db,
            wallet=wallet,
            provider=event.provider,
            provider_dispute_id=event.dispute_id,
            amount_minor=_required(
                event.amount_minor,
                "amount_minor",
            ),
            reason=event.reason,
        )

        resource_type = "chargeback_dispute"
        resource_id = dispute.id
        audit_action = "finance.chargeback.post"

        _bind_reference(
            db,
            provider=provider,
            reference_type="chargeback",
            provider_reference=event.dispute_id,
            resource_type=resource_type,
            resource_id=resource_id,
            event=event,
        )

    elif event.event_type in {
        "refund.processing",
        "refund.succeeded",
        "refund.failed",
    }:
        refund = db.get(
            Refund,
            _required(
                event.refund_id,
                "refund_id",
            ),
        )

        if refund is None:
            raise PaymentEventProcessingError(
                "Refund was not found."
            )

        _validate_resource_amount(
            event=event,
            amount_minor=refund.amount_minor,
            currency=refund.currency,
        )

        if event.event_type == "refund.processing":
            if not event.provider_reference:
                raise PaymentEventProcessingError(
                    "provider_reference is required "
                    "for refund processing."
                )

            mark_refund_processing(
                db,
                refund=refund,
                provider_reference=(
                    event.provider_reference
                ),
            )

            audit_action = (
                "finance.refund.processing"
            )

        elif event.event_type == "refund.succeeded":
            if not event.provider_reference:
                raise PaymentEventProcessingError(
                    "provider_reference is required "
                    "for successful refunds."
                )

            mark_refund_paid(
                db,
                refund=refund,
                provider_reference=(
                    event.provider_reference
                ),
                idempotency_key=(
                    f"provider:{event.provider}:"
                    f"{event.event_id}:refund-paid"
                ),
            )

            audit_action = "finance.refund.paid"

        else:
            mark_refund_failed(
                db,
                refund=refund,
                idempotency_key=(
                    f"provider:{event.provider}:"
                    f"{event.event_id}:refund-failed"
                ),
                reason=(
                    event.reason
                    or "Provider refund failed."
                ),
            )

            audit_action = "finance.refund.failed"

        resource_type = "refund"
        resource_id = refund.id

        provider_reference = (
            event.provider_reference
            or refund.external_reference
        )

        if provider_reference:
            _bind_reference(
                db,
                provider=provider,
                reference_type="refund",
                provider_reference=provider_reference,
                resource_type=resource_type,
                resource_id=resource_id,
                event=event,
            )

    elif event.event_type in {
        "payout.processing",
        "payout.paid",
        "payout.failed",
    }:
        payout = db.get(
            Payout,
            _required(
                event.payout_id,
                "payout_id",
            ),
        )

        if payout is None:
            raise PaymentEventProcessingError(
                "Payout was not found."
            )

        _validate_resource_amount(
            event=event,
            amount_minor=payout.amount_minor,
            currency=payout.currency,
        )

        if event.event_type == "payout.processing":
            if not event.provider_reference:
                raise PaymentEventProcessingError(
                    "provider_reference is required "
                    "for payout processing."
                )

            mark_payout_processing(
                db,
                payout=payout,
                provider_reference=(
                    event.provider_reference
                ),
            )

            audit_action = (
                "finance.payout.processing"
            )

        elif event.event_type == "payout.paid":
            if payout.status == "queued":
                if not event.provider_reference:
                    raise PaymentEventProcessingError(
                        "A direct payout-paid callback "
                        "requires provider_reference."
                    )

                mark_payout_processing(
                    db,
                    payout=payout,
                    provider_reference=(
                        event.provider_reference
                    ),
                )

            elif (
                event.provider_reference
                and payout.provider_reference
                and event.provider_reference
                != payout.provider_reference
            ):
                raise PaymentEventProcessingError(
                    "Payout callback provider reference "
                    "does not match the payout."
                )

            mark_payout_paid(
                db,
                payout=payout,
                idempotency_key=(
                    f"provider:{event.provider}:"
                    f"{event.event_id}:payout-paid"
                ),
            )

            audit_action = "finance.payout.paid"

        else:
            if (
                event.provider_reference
                and payout.provider_reference
                and event.provider_reference
                != payout.provider_reference
            ):
                raise PaymentEventProcessingError(
                    "Failed payout callback provider "
                    "reference does not match."
                )

            mark_payout_failed(
                db,
                payout=payout,
                idempotency_key=(
                    f"provider:{event.provider}:"
                    f"{event.event_id}:payout-failed"
                ),
                reason=(
                    event.reason
                    or "Provider payout failed."
                ),
            )

            audit_action = "finance.payout.failed"

        resource_type = "payout"
        resource_id = payout.id

        provider_reference = (
            event.provider_reference
            or payout.provider_reference
        )

        if provider_reference:
            _bind_reference(
                db,
                provider=provider,
                reference_type="payout",
                provider_reference=provider_reference,
                resource_type=resource_type,
                resource_id=resource_id,
                event=event,
            )

    elif event.event_type == "treasury.settled":
        if not event.provider_reference:
            raise PaymentEventProcessingError(
                "provider_reference is required "
                "for treasury settlement."
            )

        batch = settle_gateway_clearing_to_bank(
            db,
            provider=event.provider,
            currency=_required(
                event.currency,
                "currency",
            ),
            amount_minor=_required(
                event.amount_minor,
                "amount_minor",
            ),
            external_reference=(
                event.provider_reference
            ),
            idempotency_key=(
                f"provider:{event.provider}:"
                f"{event.event_id}:treasury"
            ),
        )

        resource_type = (
            "treasury_settlement_batch"
        )
        resource_id = batch.id
        audit_action = "finance.treasury.provider_settle"

        _bind_reference(
            db,
            provider=provider,
            reference_type="treasury_settlement",
            provider_reference=(
                event.provider_reference
            ),
            resource_type=resource_type,
            resource_id=resource_id,
            event=event,
        )

    else:
        raise PaymentEventProcessingError(
            "Unsupported normalized event type: "
            f"{event.event_type}"
        )

    if resource_id is None:
        raise PaymentEventProcessingError(
            "Provider event did not resolve "
            "an internal financial resource."
        )

    record_audit_event(
        db,
        actor_user_id=None,
        action=audit_action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        details={
            "provider": event.provider,
            "provider_event_id": event.event_id,
            "event_type": event.event_type,
            "provider_reference": (
                event.provider_reference
            ),
            "amount_minor": event.amount_minor,
            "currency": event.currency,
        },
    )

    mark_event_processed(
        db,
        event=reconciliation,
        metadata_json={
            "event_type": event.event_type,
            "resource_type": resource_type,
            "resource_id": str(resource_id),
        },
    )

    return resource_type, resource_id
