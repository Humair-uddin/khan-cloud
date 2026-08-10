from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.gateway.mikrotik_rest import MikroTikRESTAdapter
from app.models.gateway import PortMapping, PublicGateway
from app.services.gateway_reconciliation_service import (
    GatewayReconciliationError,
    reconcile_port_mapping,
)


class GatewayOrchestrationError(RuntimeError):
    pass


def build_gateway_adapter(
    gateway: PublicGateway,
) -> MikroTikRESTAdapter:
    if gateway.gateway_type != "mikrotik":
        raise GatewayOrchestrationError(
            f"Unsupported gateway type: {gateway.gateway_type}"
        )

    return MikroTikRESTAdapter(
        base_url=settings.MIKROTIK_BASE_URL,
        username=settings.MIKROTIK_USERNAME,
        password=settings.MIKROTIK_PASSWORD,
        verify_tls=settings.MIKROTIK_VERIFY_TLS,
        ca_file=settings.MIKROTIK_CA_FILE,
        timeout_seconds=settings.MIKROTIK_TIMEOUT_SECONDS,
        live_enabled=True,
    )


def _gateway_for_mapping(
    db: Session,
    mapping: PortMapping,
) -> PublicGateway:
    gateway = db.get(
        PublicGateway,
        mapping.gateway_id,
    )

    if gateway is None:
        raise GatewayOrchestrationError(
            "Public gateway not found."
        )

    if not gateway.is_active and mapping.reconcile_action == "apply":
        raise GatewayOrchestrationError(
            "Public gateway is not active."
        )

    return gateway


def reconcile_port_mapping_now(
    db: Session,
    *,
    mapping: PortMapping,
    actor_user_id: UUID | None = None,
) -> PortMapping:
    if mapping.status == "released":
        return mapping

    if not settings.MIKROTIK_LIVE_ENABLED:
        raise GatewayOrchestrationError(
            "MikroTik live reconciliation is disabled."
        )

    gateway = _gateway_for_mapping(
        db,
        mapping,
    )

    adapter = build_gateway_adapter(gateway)

    try:
        return reconcile_port_mapping(
            db,
            mapping=mapping,
            gateway=gateway,
            adapter=adapter,
            actor_user_id=actor_user_id,
        )
    except GatewayReconciliationError as exc:
        raise GatewayOrchestrationError(
            str(exc)
        ) from exc
    finally:
        adapter.close()


def reconcile_port_mapping_if_enabled(
    db: Session,
    *,
    mapping: PortMapping,
    actor_user_id: UUID | None = None,
) -> PortMapping:
    """
    Normal request-path helper.

    When live integration is disabled, desired state remains pending/
    releasing and no external gateway request is attempted.

    When enabled, reconcile immediately.
    """

    if not settings.MIKROTIK_LIVE_ENABLED:
        return mapping

    return reconcile_port_mapping_now(
        db,
        mapping=mapping,
        actor_user_id=actor_user_id,
    )
