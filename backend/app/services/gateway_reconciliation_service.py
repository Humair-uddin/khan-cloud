from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.gateway.base import GatewayAdapter
from app.integrations.gateway.factory import nat_rule_from_models
from app.models.gateway import PortMapping, PublicGateway
from app.services.audit_service import record_audit_event


class GatewayReconciliationError(RuntimeError):
    pass


RECONCILIATION_INITIAL_BACKOFF_SECONDS = 30
RECONCILIATION_MAX_BACKOFF_SECONDS = 1800


def reconciliation_backoff_seconds(
    attempt_count: int,
) -> int:
    """Return exponential retry delay capped at 30 minutes."""
    if attempt_count < 1:
        raise ValueError("attempt_count must be at least 1.")

    delay = (
        RECONCILIATION_INITIAL_BACKOFF_SECONDS
        * (2 ** (attempt_count - 1))
    )

    return min(
        delay,
        RECONCILIATION_MAX_BACKOFF_SECONDS,
    )


def _mark_reconciliation_attempt(
    mapping: PortMapping,
    *,
    attempted_at: datetime,
) -> None:
    mapping.reconcile_attempt_count += 1
    mapping.reconcile_last_attempt_at = attempted_at


def _clear_reconciliation_retry(
    mapping: PortMapping,
) -> None:
    mapping.reconcile_attempt_count = 0
    mapping.reconcile_last_attempt_at = None
    mapping.reconcile_next_attempt_at = None


def _schedule_reconciliation_retry(
    mapping: PortMapping,
    *,
    attempted_at: datetime,
) -> None:
    delay = reconciliation_backoff_seconds(
        mapping.reconcile_attempt_count
    )
    mapping.reconcile_next_attempt_at = (
        attempted_at + timedelta(seconds=delay)
    )


def reconcile_port_mapping(
    db: Session,
    *,
    mapping: PortMapping,
    gateway: PublicGateway,
    adapter: GatewayAdapter,
    actor_user_id: UUID | None = None,
) -> PortMapping:
    """
    Reconcile one PortMapping's desired state with the external gateway.

    reconcile_action="apply":
        ensure RouterOS rule exists
        success -> active
        failure -> failed, intent preserved for retry

    reconcile_action="remove":
        ensure RouterOS rule is absent
        success -> released
        failure -> failed, removal intent preserved for retry
    """

    if mapping.reconcile_action not in {"apply", "remove"}:
        raise GatewayReconciliationError(
            f"Unsupported reconciliation action: {mapping.reconcile_action}"
        )

    rule = nat_rule_from_models(
        gateway=gateway,
        mapping=mapping,
    )

    attempted_at = datetime.now(UTC)
    _mark_reconciliation_attempt(
        mapping,
        attempted_at=attempted_at,
    )

    try:
        if mapping.reconcile_action == "apply":
            result = adapter.ensure_port_mapping(rule)

            mapping.status = "active"
            mapping.reconcile_error = None
            mapping.reconciled_at = datetime.now(UTC)
            _clear_reconciliation_retry(mapping)

            if result.external_id is not None:
                mapping.external_id = result.external_id

            record_audit_event(
                db,
                actor_user_id=actor_user_id,
                action="network.port_mapping.reconciled",
                resource_type="port_mapping",
                resource_id=str(mapping.id),
                details={
                    "reconcile_action": "apply",
                    "gateway_id": str(mapping.gateway_id),
                    "vps_instance_id": str(mapping.vps_instance_id),
                    "protocol": mapping.protocol,
                    "public_port": mapping.public_port,
                    "external_id": mapping.external_id,
                    "changed": result.changed,
                    "message": result.message,
                },
            )

        else:
            result = adapter.remove_port_mapping(rule)

            mapping.status = "released"
            mapping.reconcile_error = None
            mapping.reconciled_at = datetime.now(UTC)
            mapping.released_at = datetime.now(UTC)
            mapping.external_id = None
            _clear_reconciliation_retry(mapping)

            record_audit_event(
                db,
                actor_user_id=actor_user_id,
                action="network.port_mapping.reconciled",
                resource_type="port_mapping",
                resource_id=str(mapping.id),
                details={
                    "reconcile_action": "remove",
                    "gateway_id": str(mapping.gateway_id),
                    "vps_instance_id": str(mapping.vps_instance_id),
                    "protocol": mapping.protocol,
                    "public_port": mapping.public_port,
                    "changed": result.changed,
                    "message": result.message,
                },
            )

        db.commit()
        db.refresh(mapping)

        return mapping

    except Exception as exc:
        mapping.status = "failed"
        mapping.reconcile_error = str(exc)
        _schedule_reconciliation_retry(
            mapping,
            attempted_at=attempted_at,
        )

        record_audit_event(
            db,
            actor_user_id=actor_user_id,
            action="network.port_mapping.reconciliation_failed",
            resource_type="port_mapping",
            resource_id=str(mapping.id),
            result="failed",
            reason=str(exc),
            details={
                "reconcile_action": mapping.reconcile_action,
                "gateway_id": str(mapping.gateway_id),
                "vps_instance_id": str(mapping.vps_instance_id),
                "protocol": mapping.protocol,
                "public_port": mapping.public_port,
            },
        )

        db.commit()
        db.refresh(mapping)

        raise GatewayReconciliationError(
            f"Port mapping reconciliation failed: {exc}"
        ) from exc
