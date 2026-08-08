from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class NetworkPool(BaseModel):
    __tablename__ = "network_pools"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    network_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    cidr: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    gateway: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    region: Mapped[str] = mapped_column(String(80), nullable=False, default="pk-local", index=True)
    dns_servers: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    externally_routable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class IPAllocation(BaseModel):
    __tablename__ = "ip_allocations"
    __table_args__ = (
        UniqueConstraint("pool_id", "address", name="uq_ip_allocation_pool_address"),
    )

    pool_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("network_pools.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    vps_instance_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vps_instances.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    address: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    allocation_source: Mapped[str] = mapped_column(String(40), nullable=False, default="hypervisor_dhcp")
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
