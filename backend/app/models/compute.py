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
    gaming_session_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("gaming_sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str] = mapped_column(String(500), default="")


class GamingVmBlueprint(BaseModel):
    __tablename__ = "gaming_vm_blueprints"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_gaming_vm_blueprints_slug"),
    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    template_vmid: Mapped[int] = mapped_column(Integer, nullable=False)
    storage: Mapped[str] = mapped_column(String(80), nullable=False, default="local-lvm")
    bridge: Mapped[str] = mapped_column(String(80), nullable=False, default="vmbr0")
    machine: Mapped[str] = mapped_column(String(40), nullable=False, default="q35")
    bios: Mapped[str] = mapped_column(String(20), nullable=False, default="ovmf")
    bootstrap_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="prebaked_agent_qga")
    reset_policy: Mapped[str] = mapped_column(String(40), nullable=False, default="destroy_on_terminate")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class GamingSession(BaseModel):
    __tablename__ = "gaming_sessions"

    gaming_title_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("gaming_titles.id", ondelete="RESTRICT"), nullable=True, index=True)
    product_sku_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("product_skus.id", ondelete="RESTRICT"), nullable=True, index=True)
    usage_reservation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("usage_reservations.id", ondelete="RESTRICT"), nullable=True, index=True)
    play_request_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, unique=True, index=True)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    node_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    guest_node_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    deployment_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="bare_metal", index=True)
    deployment_blueprint_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("gaming_vm_blueprints.id", ondelete="SET NULL"), nullable=True, index=True)
    guest_vm_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    deployment_stage: Mapped[str] = mapped_column(String(60), nullable=False, default="", index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    desired_state: Mapped[str] = mapped_column(String(40), nullable=False, default="running")
    minimum_vram_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    requested_cpu: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    requested_memory_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    requested_storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    gpu_uuid: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    gpu_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    gpu_vram_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streaming_backend: Mapped[str] = mapped_column(String(50), nullable=False, default="sunshine")
    billing_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="")
    per_minute_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    host_payout_per_minute_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    admission_reserved_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    pricing_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_metered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_stop_reason: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    runtime_health_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runtime_health_last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_health_last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_recovery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sanitization_state: Mapped[str] = mapped_column(String(30), nullable=False, default="", index=True)
    sanitization_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sanitization_last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sanitized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quarantine_reason: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    runtime_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    connection_info: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_category: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    failure_message: Mapped[str] = mapped_column(String(500), nullable=False, default="")


class GamingReservation(BaseModel):
    __tablename__ = "gaming_reservations"
    __table_args__ = (
        UniqueConstraint("gaming_session_id", name="uq_gaming_reservation_session"),
    )

    gaming_session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("gaming_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    gpu_uuid: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    cpu: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="reserved", index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GamingConnectionLease(BaseModel):
    __tablename__ = "gaming_connection_leases"

    gaming_session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("gaming_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )
    client_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="",
        index=True,
    )
    sunshine_client_uuid: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
        default="",
        index=True,
    )
    pairing_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    paired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    connection_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
    )
    connection_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    reconnect_grace_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    reconnect_grace_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=120,
    )
    token_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    revoked_reason: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="",
    )
    failure_message: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="",
    )
