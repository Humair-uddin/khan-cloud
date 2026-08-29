from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.finance import Payout
from app.models.payment_provider import PaymentProvider
from app.services.audit_service import (
    record_audit_event,
)
from app.services.payment_financial_outbox import (
    FinancialOutboxError,
    claim_outbox_message,
    mark_outbox_processed,
    schedule_outbox_retry,
)
from app.services.payment_payout_execution import (
    PayoutExecutionError,
    apply_payout_execution_result,
    execute_payout_with_provider,
)


class PaymentExecutionWorkerError(RuntimeError):
    pass


def process_financial_outbox_message(
    db: Session,
    *,
    outbox_id: UUID,
    actor_user_id=None,
    max_attempts: int = 8,
):
    row, duplicate = claim_outbox_message(
        db,
        outbox_id=outbox_id,
    )

    if duplicate:
        return row

    if row.available_at > datetime.now(
        timezone.utc
    ):
        row.status = "pending"
        row.locked_at = None
        db.flush()
        return row

    if row.event_type == "settlement.fetch":
        from app.services.payment_settlement_execution import (
            execute_provider_settlement_fetch,
        )

        provider_id = row.payload_json.get(
            "provider_id"
        )

        if not provider_id:
            schedule_outbox_retry(
                db,
                row=row,
                error=(
                    "Settlement fetch payload has no "
                    "provider_id."
                ),
                delay_seconds=0,
                max_attempts=1,
            )
            return row

        try:
            provider_uuid = UUID(
                str(provider_id)
            )
        except (TypeError, ValueError):
            schedule_outbox_retry(
                db,
                row=row,
                error=(
                    "Settlement fetch provider_id "
                    "is invalid."
                ),
                delay_seconds=0,
                max_attempts=1,
            )
            return row

        provider = db.get(
            PaymentProvider,
            provider_uuid,
        )

        if provider is None:
            schedule_outbox_retry(
                db,
                row=row,
                error=(
                    "Settlement fetch provider "
                    "does not exist."
                ),
                delay_seconds=0,
                max_attempts=1,
            )
            return row

        try:
            persisted = (
                execute_provider_settlement_fetch(
                    db,
                    provider=provider,
                    credential_reference=(
                        str(
                            row.payload_json.get(
                                "credential_reference"
                            )
                            or ""
                        ).strip()
                    ),
                    cursor=(
                        row.payload_json.get(
                            "cursor"
                        )
                    ),
                    outbox_idempotency_key=(
                        row.idempotency_key
                    ),
                )
            )

            mark_outbox_processed(
                db,
                row=row,
            )

            record_audit_event(
                db,
                actor_user_id=actor_user_id,
                action=(
                    "finance.settlement.fetch"
                ),
                resource_type=(
                    "payment_provider"
                ),
                resource_id=str(provider.id),
                result="processed",
                details={
                    "outbox_id": str(row.id),
                    "provider": provider.code,
                    "settlement_batch_count": (
                        len(persisted)
                    ),
                },
            )

            return row

        except Exception as exc:
            delay = min(
                30 * (
                    2 ** max(
                        row.attempt_count - 1,
                        0,
                    )
                ),
                3600,
            )

            schedule_outbox_retry(
                db,
                row=row,
                error=exc,
                delay_seconds=delay,
                max_attempts=max_attempts,
            )

            record_audit_event(
                db,
                actor_user_id=actor_user_id,
                action=(
                    "finance.settlement.fetch.error"
                ),
                resource_type=(
                    "payment_provider"
                ),
                resource_id=str(provider.id),
                result=(
                    "dead_letter"
                    if row.status == "dead_letter"
                    else "retry"
                ),
                reason=str(exc)[:500],
                details={
                    "outbox_id": str(row.id),
                    "provider": provider.code,
                    "attempt_count": (
                        row.attempt_count
                    ),
                },
            )

            return row

    if row.event_type != "payout.execute":
        schedule_outbox_retry(
            db,
            row=row,
            error=(
                "Unsupported financial outbox "
                f"event_type={row.event_type!r}"
            ),
            delay_seconds=0,
            max_attempts=1,
        )
        return row

    payout_id = row.payload_json.get(
        "payout_id"
    )

    if not payout_id:
        schedule_outbox_retry(
            db,
            row=row,
            error="Payout execution payload has no payout_id.",
            delay_seconds=0,
            max_attempts=1,
        )
        return row

    payout = db.get(
        Payout,
        UUID(str(payout_id)),
    )

    if payout is None:
        schedule_outbox_retry(
            db,
            row=row,
            error="Payout does not exist.",
            delay_seconds=0,
            max_attempts=1,
        )
        return row

    try:
        result = execute_payout_with_provider(
            db,
            payout=payout,
            credential_reference=(
                str(
                    row.payload_json.get(
                        "credential_reference"
                    )
                    or ""
                ).strip()
                or None
            ),
        )

        if (
            result.status == "failed"
            and result.retryable
        ):
            schedule_outbox_retry(
                db,
                row=row,
                error=(
                    (result.metadata or {}).get(
                        "reason",
                        "Retryable provider payout failure.",
                    )
                ),
                delay_seconds=min(
                    30 * (2 ** max(
                        row.attempt_count - 1,
                        0,
                    )),
                    3600,
                ),
                max_attempts=max_attempts,
            )

            record_audit_event(
                db,
                actor_user_id=actor_user_id,
                action="finance.payout.execution.retry",
                resource_type="payout",
                resource_id=str(payout.id),
                result="retry",
                details={
                    "outbox_id": str(row.id),
                    "attempt_count": row.attempt_count,
                },
            )

            return row

        apply_payout_execution_result(
            db,
            payout=payout,
            result=result,
            execution_idempotency_key=(
                row.idempotency_key
            ),
        )

        mark_outbox_processed(
            db,
            row=row,
        )

        record_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="finance.payout.execution",
            resource_type="payout",
            resource_id=str(payout.id),
            result=result.status,
            details={
                "outbox_id": str(row.id),
                "provider_reference": (
                    result.provider_reference
                ),
            },
        )

        return row

    except Exception as exc:
        delay = min(
            30 * (2 ** max(
                row.attempt_count - 1,
                0,
            )),
            3600,
        )

        schedule_outbox_retry(
            db,
            row=row,
            error=exc,
            delay_seconds=delay,
            max_attempts=max_attempts,
        )

        record_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="finance.payout.execution.error",
            resource_type="payout",
            resource_id=str(payout.id),
            result=(
                "dead_letter"
                if row.status == "dead_letter"
                else "retry"
            ),
            reason=str(exc)[:500],
            details={
                "outbox_id": str(row.id),
                "attempt_count": row.attempt_count,
            },
        )

        return row
