from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.gateway.base import GatewayAdapter
from app.integrations.gateway.factory import nat_rule_from_models
from app.models.gateway import PortMapping, PublicGateway
from app.services.audit_service import record_audit_event


class GatewayReconciliationError(RuntimeError):
    pass


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

    try:
        if mapping.reconcile_action == "apply":
            result = adapter.ensure_port_mapping(rule)

            mapping.status = "active"
            mapping.reconcile_error = None
            mapping.reconciled_at = datetime.now(UTC)

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
