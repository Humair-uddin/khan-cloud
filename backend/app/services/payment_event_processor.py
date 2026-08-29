from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.finance import (
    CustomerWallet,
    Payout,
    Refund,
)
from app.schemas.payment_provider import NormalizedPaymentEvent
from app.services.payment_reconciliation_service import (
    mark_event_processed,
    register_provider_event,
)
from app.services.wallet_service import confirm_deposit
from app.services.payout_service import (
    mark_payout_failed,
    mark_payout_paid,
    mark_payout_processing,
)
from app.services.refund_service import post_chargeback
from app.services.treasury_service import (
    settle_gateway_clearing_to_bank,
)


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
            UUID(resource_id) if resource_id else None,
        )

    resource_type = ""
    resource_id = None

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
                "provider_reference is required for deposits."
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

    elif event.event_type == "chargeback.created":
        wallet = _wallet(db, event.wallet_id)

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

    elif event.event_type == "payout.processing":
        payout = db.get(
            Payout,
            _required(event.payout_id, "payout_id"),
        )

        if payout is None:
            raise PaymentEventProcessingError(
                "Payout was not found."
            )

        if not event.provider_reference:
            raise PaymentEventProcessingError(
                "provider_reference is required for payout processing."
            )

        payout = mark_payout_processing(
            db,
            payout=payout,
            provider_reference=event.provider_reference,
        )

        resource_type = "payout"
        resource_id = payout.id

    elif event.event_type == "payout.paid":
        payout = db.get(
            Payout,
            _required(event.payout_id, "payout_id"),
        )

        if payout is None:
            raise PaymentEventProcessingError(
                "Payout was not found."
            )

        payout = mark_payout_paid(
            db,
            payout=payout,
            idempotency_key=(
                f"provider:{event.provider}:"
                f"{event.event_id}:payout-paid"
            ),
        )

        resource_type = "payout"
        resource_id = payout.id

    elif event.event_type == "payout.failed":
        payout = db.get(
            Payout,
            _required(event.payout_id, "payout_id"),
        )

        if payout is None:
            raise PaymentEventProcessingError(
                "Payout was not found."
            )

        payout = mark_payout_failed(
            db,
            payout=payout,
            idempotency_key=(
                f"provider:{event.provider}:"
                f"{event.event_id}:payout-failed"
            ),
            reason=event.reason or "Provider payout failed.",
        )

        resource_type = "payout"
        resource_id = payout.id

    elif event.event_type == "treasury.settled":
        if not event.provider_reference:
            raise PaymentEventProcessingError(
                "provider_reference is required for treasury settlement."
            )

        batch = settle_gateway_clearing_to_bank(
            db,
            provider=event.provider,
            currency=_required(event.currency, "currency"),
            amount_minor=_required(
                event.amount_minor,
                "amount_minor",
            ),
            external_reference=event.provider_reference,
            idempotency_key=(
                f"provider:{event.provider}:"
                f"{event.event_id}:treasury"
            ),
        )

        resource_type = "treasury_settlement_batch"
        resource_id = batch.id

    elif event.event_type in {
        "refund.succeeded",
        "refund.failed",
    }:
        refund = db.get(
            Refund,
            _required(event.refund_id, "refund_id"),
        )

        if refund is None:
            raise PaymentEventProcessingError(
                "Refund was not found."
            )

        expected_status = (
            "paid"
            if event.event_type == "refund.succeeded"
            else "failed"
        )

        if refund.status == expected_status:
            pass
        elif refund.status != "queued":
            raise PaymentEventProcessingError(
                "Refund is not in a state that accepts provider completion."
            )
        else:
            # KF-002 records provider completion state.
            # Financial refund clearing settlement/reversal remains
            # a finance-domain operation and is not bypassed here.
            refund.status = expected_status
            if event.provider_reference:
                refund.external_reference = event.provider_reference
            db.flush()

        resource_type = "refund"
        resource_id = refund.id

    else:
        raise PaymentEventProcessingError(
            f"Unsupported normalized event type: {event.event_type}"
        )

    mark_event_processed(
        db,
        event=reconciliation,
        metadata_json={
            "event_type": event.event_type,
            "resource_type": resource_type,
            "resource_id": (
                str(resource_id)
                if resource_id is not None
                else ""
            ),
        },
    )

    return resource_type, resource_id
