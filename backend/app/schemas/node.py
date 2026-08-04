from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NodeRegistrationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    machine_id: str = Field(min_length=4, max_length=255)
    hostname: str = Field(min_length=1, max_length=255)
    operating_system: str = Field(default="", max_length=255)
    kernel_version: str = Field(default="", max_length=255)
    agent_version: str = Field(default="0.1.0", max_length=50)
    management_ip: str = Field(default="", max_length=64)
    production_ip: str = Field(default="", max_length=64)
    inventory: dict[str, Any] = Field(default_factory=dict)


class NodeRegistrationResponse(BaseModel):
    node_id: UUID
    node_secret: str
    status: str


class NodeHeartbeatRequest(BaseModel):
    hostname: str = Field(min_length=1, max_length=255)
    operating_system: str = Field(default="", max_length=255)
    kernel_version: str = Field(default="", max_length=255)
    agent_version: str = Field(default="0.1.0", max_length=50)
    management_ip: str = Field(default="", max_length=64)
    production_ip: str = Field(default="", max_length=64)
    inventory: dict[str, Any] = Field(default_factory=dict)


class NodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    machine_id: str
    status: str
    is_enabled: bool
    hostname: str
    operating_system: str
    kernel_version: str
    agent_version: str
    cpu_model: str
    cpu_logical_count: int
    memory_total_bytes: int
    docker_available: bool
    nvidia_available: bool
    gpu_count: int
    management_ip: str
    production_ip: str
    inventory: dict[str, Any]
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
