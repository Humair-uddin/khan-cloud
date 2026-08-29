from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.payment_provider import PaymentProvider
from app.models.user import User
from app.schemas.payment_provider import (
    PaymentProviderCreate,
    PaymentProviderRead,
    PaymentWebhookResult,
)
from app.services.audit_service import record_audit_event
from app.services.payment_provider_service import (
    PaymentProviderError,
    create_provider,
    get_provider,
)
from app.services.payment_webhook_service import (
    PaymentWebhookError,
    process_provider_webhook,
)


router = APIRouter(
    prefix="/payment-providers",
    tags=["payment-providers"],
)


def _provider_read(provider: PaymentProvider) -> PaymentProviderRead:
    return PaymentProviderRead(
        id=provider.id,
        code=provider.code,
        display_name=provider.display_name,
        adapter_type=provider.adapter_type,
        environment=provider.environment,
        enabled=provider.enabled,
        capabilities=dict(provider.capabilities_json or {}),
        supported_currencies=list(
            provider.supported_currencies_json or []
        ),
        status=provider.status,
        webhook_tolerance_seconds=provider.webhook_tolerance_seconds,
    )


@router.post(
    "/operator",
    response_model=PaymentProviderRead,
)
def operator_create_provider(
    payload: PaymentProviderCreate,
    user: User = Depends(
        require_permission("finance.payment_providers.manage")
    ),
    db: Session = Depends(get_db),
):
    try:
        provider = create_provider(
            db,
            code=payload.code,
            display_name=payload.display_name,
            adapter_type=payload.adapter_type,
            environment=payload.environment,
            enabled=payload.enabled,
            capabilities=payload.capabilities,
            supported_currencies=payload.supported_currencies,
            credential_reference=payload.credential_reference,
            webhook_secret_reference=payload.webhook_secret_reference,
            webhook_tolerance_seconds=payload.webhook_tolerance_seconds,
        )

        record_audit_event(
            db,
            actor_user_id=user.id,
            action="finance.payment_provider.create",
            resource_type="payment_provider",
            resource_id=str(provider.id),
            details={
                "code": provider.code,
                "environment": provider.environment,
                "enabled": provider.enabled,
            },
        )

        db.commit()
        db.refresh(provider)

        return _provider_read(provider)

    except PaymentProviderError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get(
    "/operator",
    response_model=list[PaymentProviderRead],
)
def operator_list_providers(
    user: User = Depends(
        require_permission("finance.payment_providers.manage")
    ),
    db: Session = Depends(get_db),
):
    providers = db.scalars(
        select(PaymentProvider).order_by(
            PaymentProvider.code
        )
    ).all()

    return [_provider_read(p) for p in providers]


@router.post(
    "/webhooks/{provider_code}",
    response_model=PaymentWebhookResult,
)
async def receive_provider_webhook(
    provider_code: str,
    request: Request,
    db: Session = Depends(get_db),
):
    import json

    from app.services.payment_provider_policy import (
        PaymentProviderPolicyError,
    )
    from app.services.payment_secret_resolver import (
        PaymentSecretError,
    )
    from app.services.payment_webhook_forensics import (
        build_forensic_record,
        persist_forensic_record_independent,
    )
    from app.services.payment_webhook_outcome import (
        WebhookOutcomeCode,
        webhook_http_outcome,
    )

    raw_body = await request.body()

    headers = {
        key.lower(): value
        for key, value in request.headers.items()
    }

    provider = None
    event_id = "unresolved"
    payload_for_forensics = {
        "raw_body_sha256": __import__(
            "hashlib"
        ).sha256(raw_body).hexdigest(),
    }

    try:
        decoded = json.loads(
            raw_body.decode("utf-8")
        )
        if isinstance(decoded, dict):
            candidate = (
                decoded.get("event_id")
                or decoded.get("id")
            )
            if candidate:
                event_id = str(candidate)[:255]
    except Exception:
        pass

    def forensic_signature():
        for key in (
            "x-signature",
            "x-webhook-signature",
            "stripe-signature",
            "signature",
        ):
            if key in headers:
                return headers[key]
        return None

    def persist_outcome(
        *,
        code,
        error=None,
    ):
        outcome = webhook_http_outcome(
            code
        )

        record = build_forensic_record(
            provider_code=(
                provider.code
                if provider is not None
                else provider_code.strip().lower()
                or "unknown"
            ),
            event_id=event_id,
            payload=payload_for_forensics,
            signature=forensic_signature(),
            outcome_code=outcome.code.value,
            http_status=outcome.http_status,
            retryable=outcome.retryable,
            error=error,
        )

        persist_forensic_record_independent(
            record=record
        )

        return outcome

    try:
        provider = get_provider(
            db,
            code=provider_code,
            require_enabled=True,
        )

        receipt, replay = (
            process_provider_webhook(
                db,
                provider=provider,
                raw_body=raw_body,
                headers=headers,
            )
        )

        event_id = receipt.event_id

        if not replay:
            record_audit_event(
                db,
                actor_user_id=None,
                action=(
                    "finance.payment_webhook.process"
                ),
                resource_type=(
                    "payment_webhook_receipt"
                ),
                resource_id=str(receipt.id),
                details={
                    "provider": provider.code,
                    "event_id": receipt.event_id,
                    "event_type": receipt.event_type,
                    "processing_status": (
                        receipt.processing_status
                    ),
                },
            )

        db.commit()

        persist_outcome(
            code=(
                WebhookOutcomeCode.DUPLICATE
                if replay
                else WebhookOutcomeCode.ACCEPTED
            )
        )

        return PaymentWebhookResult(
            receipt_id=receipt.id,
            provider=provider.code,
            event_id=receipt.event_id,
            event_type=receipt.event_type,
            status=receipt.processing_status,
            replay=replay,
            resource_type=(
                receipt.result_resource_type
            ),
            resource_id=(
                receipt.result_resource_id
            ),
        )

    except (
        PaymentProviderError,
        PaymentWebhookError,
        PaymentProviderPolicyError,
        PaymentSecretError,
    ) as exc:
        db.rollback()

        message = str(exc).lower()

        if "signature" in message:
            code = (
                WebhookOutcomeCode.INVALID_SIGNATURE
            )
        elif (
            "timestamp" in message
            or "replay window" in message
        ):
            code = WebhookOutcomeCode.STALE
        elif "disabled" in message:
            code = (
                WebhookOutcomeCode.PROVIDER_DISABLED
            )
        elif "capability" in message:
            code = (
                WebhookOutcomeCode.UNSUPPORTED_CAPABILITY
            )
        elif (
            "currency" in message
            or "fx" in message
        ):
            code = (
                WebhookOutcomeCode.UNSUPPORTED_CURRENCY
            )
        elif (
            "different raw contents" in message
            or "different normalized contents"
            in message
            or "different event type" in message
        ):
            code = (
                WebhookOutcomeCode.CONTENT_CONFLICT
            )
        else:
            code = (
                WebhookOutcomeCode.DOMAIN_REJECTED
            )

        outcome = persist_outcome(
            code=code,
            error=exc,
        )

        raise HTTPException(
            status_code=outcome.http_status,
            detail={
                "code": outcome.code.value,
                "retryable": outcome.retryable,
                "message": str(exc),
            },
        ) from exc

    except Exception as exc:
        db.rollback()

        outcome = persist_outcome(
            code=(
                WebhookOutcomeCode.INTERNAL_FAILURE
            ),
            error=exc,
        )

        raise HTTPException(
            status_code=outcome.http_status,
            detail={
                "code": outcome.code.value,
                "retryable": outcome.retryable,
                "message": (
                    "Provider webhook processing "
                    "failed."
                ),
            },
        ) from exc
