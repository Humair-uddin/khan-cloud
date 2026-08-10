from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.compute import VPSInstance
from app.models.gateway import PortMapping, PublicGateway
from app.models.user import User
from app.schemas.network import PublicGatewayCreate
from app.services.audit_service import record_audit_event


DEFAULT_PUBLIC_PORT_START = 20000
DEFAULT_PUBLIC_PORT_END = 29999


class GatewayError(ValueError):
    pass


def _normalize_protocol(protocol: str) -> str:
    value = protocol.strip().lower()

    if value not in {"tcp", "udp"}:
        raise GatewayError("Protocol must be tcp or udp.")

    return value


def _validate_ip(address: str) -> str:
    try:
        return str(ipaddress.ip_address(address))
    except ValueError as exc:
        raise GatewayError("Invalid IP address.") from exc


def list_public_gateways(
    db: Session,
    *,
    active_only: bool = True,
) -> list[PublicGateway]:
    stmt = select(PublicGateway).order_by(
        PublicGateway.region,
        PublicGateway.name,
    )

    if active_only:
        stmt = stmt.where(PublicGateway.is_active.is_(True))

    return list(db.scalars(stmt).unique())


def get_public_gateway(
    db: Session,
    gateway_id: UUID,
) -> PublicGateway:
    gateway = db.get(PublicGateway, gateway_id)

    if gateway is None:
        raise GatewayError("Public gateway not found.")

    return gateway


def get_port_mapping(
    db: Session,
    mapping_id: UUID,
) -> PortMapping:
    mapping = db.get(PortMapping, mapping_id)

    if mapping is None:
        raise GatewayError("Port mapping not found.")

    return mapping


def create_public_gateway(
    db: Session,
    *,
    payload: PublicGatewayCreate,
    actor: User,
) -> PublicGateway:
    public_ip = _validate_ip(payload.public_ip)

    if db.scalar(
        select(PublicGateway).where(
            PublicGateway.slug == payload.slug
        )
    ):
        raise GatewayError("Gateway slug already exists.")

    if db.scalar(
        select(PublicGateway).where(
            PublicGateway.public_ip == public_ip
        )
    ):
        raise GatewayError("Public IP is already registered.")

    gateway = PublicGateway(
        name=payload.name,
        slug=payload.slug,
        public_ip=public_ip,
        provider=payload.provider,
        region=payload.region,
        gateway_type=payload.gateway_type,
        is_active=True,
    )

    db.add(gateway)
    db.flush()

    record_audit_event(
        db,
        actor_user_id=actor.id,
        action="network.gateway.created",
        resource_type="public_gateway",
        resource_id=str(gateway.id),
        details={
            "slug": gateway.slug,
            "public_ip": gateway.public_ip,
            "gateway_type": gateway.gateway_type,
        },
    )

    db.commit()
    db.refresh(gateway)

    return gateway


def _used_ports(
    db: Session,
    *,
    gateway_id: UUID,
    protocol: str,
) -> set[int]:
    return set(
        db.scalars(
            select(PortMapping.public_port).where(
                PortMapping.gateway_id == gateway_id,
                PortMapping.protocol == protocol,
                PortMapping.status != "released",
            )
        ).all()
    )


def _next_available_port(
    db: Session,
    *,
    gateway_id: UUID,
    protocol: str,
    start: int = DEFAULT_PUBLIC_PORT_START,
    end: int = DEFAULT_PUBLIC_PORT_END,
) -> int:
    if start < 1 or end > 65535 or start > end:
        raise GatewayError("Invalid public port allocation range.")

    used = _used_ports(
        db,
        gateway_id=gateway_id,
        protocol=protocol,
    )

    for port in range(start, end + 1):
        if port not in used:
            return port

    raise GatewayError("No public ports are available.")


def allocate_port_mapping(
    db: Session,
    *,
    gateway: PublicGateway,
    vps: VPSInstance,
    protocol: str,
    private_port: int,
    actor: User,
    public_port: int | None = None,
) -> PortMapping:
    if not gateway.is_active:
        raise GatewayError("Gateway is not active.")

    if vps.status == "deleted":
        raise GatewayError("Cannot allocate a port to a deleted VPS.")

    if not vps.primary_ip:
        raise GatewayError("VPS does not have a private IP address.")

    private_ip = _validate_ip(vps.primary_ip)
    normalized_protocol = _normalize_protocol(protocol)

    if not 1 <= private_port <= 65535:
        raise GatewayError(
            "Private port must be between 1 and 65535."
        )

    if public_port is None:
        selected_public_port = _next_available_port(
            db,
            gateway_id=gateway.id,
            protocol=normalized_protocol,
        )
    else:
        if not 1 <= public_port <= 65535:
            raise GatewayError(
                "Public port must be between 1 and 65535."
            )

        existing = db.scalar(
            select(PortMapping).where(
                PortMapping.gateway_id == gateway.id,
                PortMapping.protocol == normalized_protocol,
                PortMapping.public_port == public_port,
                PortMapping.status != "released",
            )
        )

        if existing is not None:
            raise GatewayError(
                "Public endpoint is already allocated."
            )

        selected_public_port = public_port

    mapping = PortMapping(
        gateway_id=gateway.id,
        vps_instance_id=vps.id,
        organization_id=vps.organization_id,
        protocol=normalized_protocol,
        public_port=selected_public_port,
        private_ip=private_ip,
        private_port=private_port,
        status="allocated",
        allocation_source="control_plane",
        allocated_at=datetime.now(UTC),
    )

    try:
        with db.begin_nested():
            db.add(mapping)
            db.flush()
    except IntegrityError as exc:
        raise GatewayError(
            "Public endpoint was allocated concurrently."
        ) from exc

    record_audit_event(
        db,
        actor_user_id=actor.id,
        action="network.port_mapping.allocated",
        resource_type="port_mapping",
        resource_id=str(mapping.id),
        details={
            "gateway_id": str(gateway.id),
            "vps_instance_id": str(vps.id),
            "protocol": mapping.protocol,
            "public_port": mapping.public_port,
            "private_ip": mapping.private_ip,
            "private_port": mapping.private_port,
        },
    )

    db.commit()
    db.refresh(mapping)

    return mapping


def release_port_mapping(
    db: Session,
    *,
    mapping: PortMapping,
    actor: User,
) -> PortMapping:
    if mapping.status == "released":
        return mapping

    mapping.status = "released"
    mapping.released_at = datetime.now(UTC)

    record_audit_event(
        db,
        actor_user_id=actor.id,
        action="network.port_mapping.released",
        resource_type="port_mapping",
        resource_id=str(mapping.id),
        details={
            "gateway_id": str(mapping.gateway_id),
            "vps_instance_id": str(mapping.vps_instance_id),
            "protocol": mapping.protocol,
            "public_port": mapping.public_port,
        },
    )

    db.commit()
    db.refresh(mapping)

    return mapping


def release_vps_port_mappings(
    db: Session,
    *,
    vps_id: UUID,
) -> int:
    mappings = list(
        db.scalars(
            select(PortMapping).where(
                PortMapping.vps_instance_id == vps_id,
                PortMapping.status != "released",
            )
        ).unique()
    )

    if not mappings:
        return 0

    now = datetime.now(UTC)

    for mapping in mappings:
        mapping.status = "released"
        mapping.released_at = now

        record_audit_event(
            db,
            actor_user_id=None,
            action="network.port_mapping.released",
            resource_type="port_mapping",
            resource_id=str(mapping.id),
            reason="VPS lifecycle deletion",
            details={
                "gateway_id": str(mapping.gateway_id),
                "vps_instance_id": str(mapping.vps_instance_id),
                "protocol": mapping.protocol,
                "public_port": mapping.public_port,
                "release_source": "vps_delete",
            },
        )

    return len(mappings)


def list_vps_port_mappings(
    db: Session,
    *,
    vps_id: UUID,
    active_only: bool = True,
) -> list[PortMapping]:
    stmt = (
        select(PortMapping)
        .where(PortMapping.vps_instance_id == vps_id)
        .order_by(
            PortMapping.protocol,
            PortMapping.public_port,
        )
    )

    if active_only:
        stmt = stmt.where(
            PortMapping.status != "released"
        )

    return list(db.scalars(stmt).unique())
