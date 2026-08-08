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


class VPSCreate(BaseModel):
    organization_id: UUID | None = None
    name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    image: str = Field(default="ubuntu-24.04", pattern=r"^[A-Za-z0-9_.:-]+$")
    vcpu: int = Field(ge=1, le=128)
    memory_mb: int = Field(ge=512, le=1048576)
    disk_gb: int = Field(ge=8, le=16384)


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
    job_type: str
    payload: dict[str, Any]
    status: str
    attempt_count: int


class NodeJobResult(BaseModel):
    status: Literal["succeeded", "failed", "blocked"]
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str = Field(default="", max_length=500)
