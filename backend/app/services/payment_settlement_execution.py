from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.payment_provider import PaymentProvider
from app.services.payment_adapter_registry import (
    ProviderSettlementBatchResult,
    create_adapter_for_provider,
)
from app.services.payment_financial_outbox import (
    enqueue_outbox_message,
)
from app.services.payment_provider_policy import (
    ProviderOperationPolicy,
    enforce_provider_operation,
)
from app.services.payment_secret_resolver import (
    resolve_secret,
)
from app.services.payment_settlement_service import (
    ingest_provider_settlement,
)


class PaymentSettlementExecutionError(RuntimeError):
    pass


def enqueue_provider_settlement_fetch(
    db: Session,
    *,
    provider: PaymentProvider,
    idempotency_key: str,
    cursor: str | None = None,
):
    return enqueue_outbox_message(
        db,
        event_type="settlement.fetch",
        aggregate_type="payment_provider",
        aggregate_id=str(provider.id),
        idempotency_key=idempotency_key,
        payload={
            "provider_id": str(provider.id),
            "cursor": cursor,
            # This is an external secret locator, never the secret.
            # Snapshotting it preserves in-flight credential-version
            # semantics when configuration later rotates.
            "credential_reference": (
                provider.credential_reference
            ),
        },
    )


def execute_provider_settlement_fetch(
    db: Session,
    *,
    provider: PaymentProvider,
    credential_reference: str,
    cursor: str | None,
    outbox_idempotency_key: str,
) -> list:
    enforce_provider_operation(
        provider,
        ProviderOperationPolicy(
            capability="treasury_settlement",
        ),
    )

    credential_reference = str(
        credential_reference or ""
    ).strip()

    credential = (
        resolve_secret(credential_reference)
        if credential_reference
        else None
    )

    adapter = create_adapter_for_provider(
        provider,
        credential=credential,
    )

    fetch = getattr(
        adapter,
        "fetch_settlement_batches",
        None,
    )

    if not callable(fetch):
        raise PaymentSettlementExecutionError(
            "Payment adapter does not implement "
            "fetch_settlement_batches()."
        )

    results = fetch(
        cursor=cursor,
    )

    if not isinstance(results, list):
        raise PaymentSettlementExecutionError(
            "Provider settlement result must be a list."
        )

    persisted = []

    for index, result in enumerate(results):
        if isinstance(
            result,
            ProviderSettlementBatchResult,
        ):
            reference = (
                result.provider_settlement_reference
            )
            currency = result.settlement_currency
            settlement_date = result.settlement_date
            items = list(result.items)
            metadata = dict(result.metadata or {})
        elif isinstance(result, dict):
            reference = str(
                result.get(
                    "provider_settlement_reference"
                )
                or ""
            )
            currency = str(
                result.get("settlement_currency")
                or ""
            )
            settlement_date = result.get(
                "settlement_date"
            )
            items = list(
                result.get("items") or []
            )
            metadata = dict(
                result.get("metadata") or {}
            )
        else:
            raise PaymentSettlementExecutionError(
                "Unsupported provider settlement result."
            )

        batch, replay = ingest_provider_settlement(
            db,
            provider=provider,
            provider_settlement_reference=reference,
            settlement_currency=currency,
            settlement_date=settlement_date,
            items=items,
            idempotency_key=(
                f"{outbox_idempotency_key}:"
                f"{index}:{reference}"
            ),
            credential_reference_snapshot=(
                credential_reference
            ),
            metadata_json=metadata,
        )

        persisted.append(
            (batch, replay)
        )

    return persisted
