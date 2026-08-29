from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finance import Payout, PayoutMethod
from app.models.payment_provider import PaymentProvider
from app.services.payment_adapter_registry import (
    PaymentAdapterError,
    create_adapter_for_provider,
)
from app.services.payment_provider_policy import (
    ProviderOperationPolicy,
    enforce_provider_operation,
)
from app.services.payment_secret_resolver import (
    resolve_secret,
)
from app.services.payout_service import (
    PayoutError,
    mark_payout_failed,
    mark_payout_paid,
    mark_payout_processing,
)


class PayoutExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PayoutExecutionResult:
    provider_reference: str
    status: str
    retryable: bool = False
    metadata: dict[str, Any] | None = None


def provider_for_payout(
    db: Session,
    *,
    payout: Payout,
) -> PaymentProvider:
    method = db.get(
        PayoutMethod,
        payout.payout_method_id,
    )

    if method is None:
        raise PayoutExecutionError(
            "Payout method was not found."
        )

    provider = db.scalar(
        select(PaymentProvider).where(
            PaymentProvider.code
            == method.provider.strip().lower()
        )
    )

    if provider is None:
        raise PayoutExecutionError(
            "Configured payment provider was not found."
        )

    enforce_provider_operation(
        provider,
        ProviderOperationPolicy(
            capability="payouts",
            currency=payout.currency,
            presentment_currency=payout.currency,
            settlement_currency=payout.currency,
            allow_explicit_fx=False,
        ),
    )

    return provider


def execute_payout_with_provider(
    db: Session,
    *,
    payout: Payout,
) -> PayoutExecutionResult:
    provider = provider_for_payout(
        db,
        payout=payout,
    )

    method = db.get(
        PayoutMethod,
        payout.payout_method_id,
    )

    assert method is not None

    try:
        adapter = create_adapter_for_provider(
            provider,
            credential=(
                resolve_secret(
                    provider.credential_reference
                )
                if provider.credential_reference
                else None
            ),
        )
    except Exception as exc:
        raise PayoutExecutionError(
            f"Provider adapter initialization failed: {exc}"
        ) from exc

    execute = getattr(
        adapter,
        "execute_payout",
        None,
    )

    if not callable(execute):
        raise PayoutExecutionError(
            "Payment adapter does not implement execute_payout()."
        )

    response = execute(
        payout_id=str(payout.id),
        amount_minor=payout.amount_minor,
        currency=payout.currency,
        payout_method={
            "method_type": method.method_type,
            "provider": method.provider,
            "country_code": method.country_code,
            "currency": method.currency,
            "encrypted_payload": method.encrypted_payload,
            "encryption_key_version": (
                method.encryption_key_version
            ),
            "fingerprint": method.fingerprint,
            "last4": method.last4,
        },
        idempotency_key=payout.idempotency_key,
    )

    if isinstance(response, PayoutExecutionResult):
        return response

    if not isinstance(response, dict):
        raise PayoutExecutionError(
            "Provider payout response must be a mapping."
        )

    provider_reference = str(
        response.get("provider_reference") or ""
    ).strip()

    status = str(
        response.get("status") or ""
    ).strip().lower()

    if status not in {
        "processing",
        "paid",
        "failed",
    }:
        raise PayoutExecutionError(
            "Provider returned an unsupported payout status."
        )

    if status in {
        "processing",
        "paid",
    } and not provider_reference:
        raise PayoutExecutionError(
            "Provider payout reference is required."
        )

    return PayoutExecutionResult(
        provider_reference=provider_reference,
        status=status,
        retryable=bool(
            response.get("retryable", False)
        ),
        metadata=dict(
            response.get("metadata") or {}
        ),
    )


def apply_payout_execution_result(
    db: Session,
    *,
    payout: Payout,
    result: PayoutExecutionResult,
    execution_idempotency_key: str,
) -> Payout:
    if result.status == "processing":
        return mark_payout_processing(
            db,
            payout=payout,
            provider_reference=(
                result.provider_reference
            ),
        )

    if result.status == "paid":
        mark_payout_processing(
            db,
            payout=payout,
            provider_reference=(
                result.provider_reference
            ),
        )

        return mark_payout_paid(
            db,
            payout=payout,
            idempotency_key=(
                f"ledger:{execution_idempotency_key}:paid"
            ),
        )

    if result.status == "failed":
        return mark_payout_failed(
            db,
            payout=payout,
            idempotency_key=(
                f"ledger:{execution_idempotency_key}:failed"
            ),
            reason=(
                str(
                    (result.metadata or {}).get(
                        "reason",
                        "Provider payout failed.",
                    )
                )
            ),
        )

    raise PayoutExecutionError(
        "Unsupported payout execution result."
    )
