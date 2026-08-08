from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class NodeCapacity(BaseModel):
    __tablename__ = "node_capacities"
    __table_args__ = (UniqueConstraint("node_id", name="uq_node_capacities_node_id"),)

    node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cpu_total: Mapped[int] = mapped_column(Integer, default=0)
    cpu_reserved_host: Mapped[int] = mapped_column(Integer, default=0)
    cpu_allocatable: Mapped[int] = mapped_column(Integer, default=0)
    cpu_allocated: Mapped[int] = mapped_column(Integer, default=0)
    memory_total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    memory_reserved_host_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    memory_allocatable_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    memory_allocated_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_reserved_host_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_allocatable_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    storage_allocated_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    kvm_available: Mapped[bool] = mapped_column(Boolean, default=False)
    libvirt_available: Mapped[bool] = mapped_column(Boolean, default=False)
    virtualization_ready: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    execution_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    scheduling_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



class ProvisioningAuthorization(BaseModel):
    __tablename__ = "provisioning_authorizations"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="authorized", index=True)
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    reference_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VPSInstance(BaseModel):

    __tablename__ = "vps_instances"

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    node_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provisioning_authorization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("provisioning_authorizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    image: Mapped[str] = mapped_column(String(100), nullable=False, default="ubuntu-24.04")
    vcpu: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disk_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    desired_state: Mapped[str] = mapped_column(String(40), default="running", nullable=False)
    runtime_id: Mapped[str] = mapped_column(String(255), default="")
    primary_ip: Mapped[str] = mapped_column(String(64), default="")
    access_username: Mapped[str] = mapped_column(String(64), default="ubuntu")
    ssh_public_key_fingerprint: Mapped[str] = mapped_column(String(128), default="")
    guest_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_category: Mapped[str] = mapped_column(String(80), default="")
    failure_message: Mapped[str] = mapped_column(String(500), default="")


class ResourceReservation(BaseModel):
    __tablename__ = "resource_reservations"
    __table_args__ = (UniqueConstraint("vps_instance_id", name="uq_resource_reservation_vps"),)

    vps_instance_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vps_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cpu: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="reserved", nullable=False, index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NodeJob(BaseModel):
    __tablename__ = "node_jobs"

    node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vps_instance_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vps_instances.id", ondelete="CASCADE"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str] = mapped_column(String(500), default="")
