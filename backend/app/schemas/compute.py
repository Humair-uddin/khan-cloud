from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CapacityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    node_id: UUID
    cpu_total: int
    cpu_reserved_host: int
    cpu_allocatable: int
    cpu_allocated: int
    cpu_available: int
    memory_total_bytes: int
    memory_reserved_host_bytes: int
    memory_allocatable_bytes: int
    memory_allocated_bytes: int
    memory_available_bytes: int
    storage_total_bytes: int
    storage_reserved_host_bytes: int
    storage_allocatable_bytes: int
    storage_allocated_bytes: int
    storage_available_bytes: int
    kvm_available: bool
    libvirt_available: bool
    virtualization_ready: bool
    execution_enabled: bool
    scheduling_enabled: bool
    readiness_reasons: list[str] = Field(default_factory=list)
    last_refreshed_at: datetime | None


class ComputeHostRead(BaseModel):
    node_id: UUID
    name: str
    hostname: str
    connectivity_state: str
    lifecycle_state: str
    intended_purpose: str
    capacity: CapacityRead



class ProvisioningAuthorizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    source: str
    status: str
    reference_type: str
    reference_id: str
    expires_at: datetime | None
    consumed_at: datetime | None


class VPSImageRead(BaseModel):
    slug: str
    name: str
    operating_system: str
    version: str
    access_username: str
    supports_cloud_init: bool


class VPSCreate(BaseModel):

    organization_id: UUID | None = None
    provisioning_authorization_id: UUID | None = None
    name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    image: str = Field(default="ubuntu-24.04", pattern=r"^[A-Za-z0-9_.:-]+$")
    vcpu: int = Field(ge=1, le=128)
    memory_mb: int = Field(ge=512, le=1048576)
    disk_gb: int = Field(ge=8, le=16384)
    ssh_public_key: str = Field(min_length=40, max_length=4096)


class VPSRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    node_id: UUID | None
    name: str
    image: str
    vcpu: int
    memory_bytes: int
    disk_bytes: int
    status: str
    desired_state: str
    runtime_id: str
    primary_ip: str
    access_username: str
    ssh_public_key_fingerprint: str
    guest_ready_at: datetime | None
    failure_category: str
    failure_message: str
    created_at: datetime
    updated_at: datetime


class VPSAction(BaseModel):
    action: Literal["start", "stop", "reboot", "delete"]


class NodeJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    node_id: UUID
    vps_instance_id: UUID | None
    gaming_session_id: UUID | None = None
    job_type: str
    payload: dict[str, Any]
    status: str
    attempt_count: int


class NodeJobResult(BaseModel):
    status: Literal["succeeded", "failed", "blocked"]
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str = Field(default="", max_length=500)


class GamingSessionCreate(BaseModel):
    game_slug: str | None = None
    play_request_id: UUID | None = None
    deployment_mode: Literal["bare_metal", "proxmox_windows_vm"] = "bare_metal"
    blueprint_slug: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    organization_id: UUID | None = None
    name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    minimum_vram_mb: int = Field(default=8192, ge=8192, le=196608)
    cpu: int = Field(default=2, ge=1, le=128)
    memory_mb: int = Field(default=4096, ge=1024, le=1048576)
    storage_gb: int = Field(default=20, ge=1, le=16384)
    streaming_backend: Literal["sunshine"] = "sunshine"


    # KG-008K22 scheduler/display intent.
    # These are business/client constraints only; the VDD driver
    # remains bounded by the validated capability envelope.
    display_profile: str = "auto"
    display_max_width: int | None = None
    display_max_height: int | None = None
    display_max_refresh_hz: int | None = None
    display_preferred_width: int | None = None
    display_preferred_height: int | None = None
    display_preferred_refresh_hz: int | None = None
    hdr_requested: bool = False
    client_hdr_capable: bool = False
    display_allow_4k: bool | None = None
    display_allow_240hz: bool | None = None

class GamingSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    node_id: UUID | None
    guest_node_id: UUID | None
    gaming_title_id: UUID | None
    product_sku_id: UUID | None
    usage_reservation_id: UUID | None
    play_request_id: UUID | None
    deployment_mode: str
    deployment_blueprint_id: UUID | None
    guest_vm_id: int | None
    deployment_stage: str
    name: str
    status: str
    desired_state: str
    minimum_vram_mb: int
    requested_cpu: int
    requested_memory_bytes: int
    requested_storage_bytes: int
    gpu_uuid: str
    gpu_name: str
    gpu_vram_mb: int
    streaming_backend: str
    billing_currency: str
    per_minute_price_minor: int
    host_payout_per_minute_minor: int
    admission_reserved_minor: int
    pricing_snapshot: dict[str, Any]
    last_metered_at: datetime | None
    billing_finalized_at: datetime | None
    billing_stop_reason: str
    runtime_id: str
    connection_info: dict[str, Any]
    started_at: datetime | None
    ended_at: datetime | None
    failure_category: str
    failure_message: str
    created_at: datetime
    updated_at: datetime


class GamingSessionAction(BaseModel):
    action: Literal["start", "stop", "terminate"]


class GamingConnectionLeaseCreate(BaseModel):
    pairing_ttl_seconds: int = Field(
        default=300,
        ge=60,
        le=900,
    )


class GamingConnectionPairRequest(BaseModel):
    pin: str = Field(
        min_length=4,
        max_length=4,
        pattern=r"^[0-9]{4}$",
    )


class GamingConnectionLeaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gaming_session_id: UUID
    organization_id: UUID
    user_id: UUID
    node_id: UUID
    state: str
    client_name: str
    sunshine_client_uuid: str
    pairing_expires_at: datetime
    paired_at: datetime | None
    revoked_at: datetime | None
    failure_message: str
    created_at: datetime
    updated_at: datetime


class GamingVmBlueprintCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=2, max_length=150)
    enabled: bool = False
    template_vmid: int = Field(ge=100, le=999999999)
    storage: str = Field(default="local-lvm", min_length=1, max_length=80)
    bridge: str = Field(default="vmbr0", min_length=1, max_length=80)
    machine: Literal["q35"] = "q35"
    bios: Literal["ovmf"] = "ovmf"
    bootstrap_mode: Literal["prebaked_agent_qga"] = "prebaked_agent_qga"
    reset_policy: Literal["destroy_on_terminate"] = "destroy_on_terminate"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class GamingVmBlueprintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    slug: str
    name: str
    enabled: bool
    template_vmid: int
    storage: str
    bridge: str
    machine: str
    bios: str
    bootstrap_mode: str
    reset_policy: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
