from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compute import VPSInstance
from app.models.network import IPAllocation, NetworkPool
from app.models.user import User
from app.schemas.network import VPSNetworkRead
from app.services.organization_service import user_can_access_organization


class NetworkError(ValueError):
    pass


def list_network_pools(db: Session, *, active_only: bool = True) -> list[NetworkPool]:
    stmt = select(NetworkPool).order_by(NetworkPool.region, NetworkPool.name)
    if active_only:
        stmt = stmt.where(NetworkPool.is_active.is_(True))
    return list(db.scalars(stmt).unique())


def _pool_for_address(db: Session, address: str) -> NetworkPool | None:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    for pool in list_network_pools(db):
        try:
            if ip in ipaddress.ip_network(pool.cidr, strict=False):
                return pool
        except ValueError:
            continue
    return None


def record_runtime_allocation(db: Session, *, vps: VPSInstance, address: str) -> IPAllocation:
    pool = _pool_for_address(db, address)
    if pool is None:
        raise NetworkError(f"No active Khan Cloud network pool contains {address}.")

    existing = db.scalar(
        select(IPAllocation).where(
            IPAllocation.pool_id == pool.id,
            IPAllocation.address == address,
        )
    )
    if existing is not None:
        if existing.status == "active" and existing.vps_instance_id != vps.id:
            raise NetworkError(f"IP address {address} is already allocated.")
        existing.vps_instance_id = vps.id
        existing.organization_id = vps.organization_id
        existing.status = "active"
        existing.released_at = None
        existing.allocated_at = datetime.now(UTC)
        return existing

    allocation = IPAllocation(
        pool_id=pool.id,
        vps_instance_id=vps.id,
        organization_id=vps.organization_id,
        address=address,
        status="active",
        allocation_source="hypervisor_dhcp",
        allocated_at=datetime.now(UTC),
    )
    db.add(allocation)
    db.flush()
    return allocation


def release_vps_addresses(db: Session, *, vps_id: UUID) -> None:
    allocations = list(db.scalars(
        select(IPAllocation).where(
            IPAllocation.vps_instance_id == vps_id,
            IPAllocation.status == "active",
        )
    ).unique())
    now = datetime.now(UTC)
    for item in allocations:
        item.status = "released"
        item.released_at = now


def visible_vps_network(db: Session, *, user: User, vps: VPSInstance) -> VPSNetworkRead:
    if not user_can_access_organization(db, user, vps.organization_id):
        raise NetworkError("VPS not found.")
    rows = list(db.execute(
        select(IPAllocation, NetworkPool)
        .join(NetworkPool, NetworkPool.id == IPAllocation.pool_id)
        .where(
            IPAllocation.vps_instance_id == vps.id,
            IPAllocation.status == "active",
        )
    ).all())
    private_addresses: list[str] = []
    public_addresses: list[str] = []
    for allocation, pool in rows:
        if pool.externally_routable:
            public_addresses.append(allocation.address)
        else:
            private_addresses.append(allocation.address)
    return VPSNetworkRead(
        primary_ip=vps.primary_ip,
        private_addresses=private_addresses,
        public_addresses=public_addresses,
        network_status="allocated" if rows else ("pending" if vps.status == "provisioning" else "unassigned"),
    )
