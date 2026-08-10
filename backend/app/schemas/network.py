from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NetworkPoolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    network_type: str
    cidr: str
    gateway: str
    region: str
    dns_servers: list[str]
    is_active: bool
    is_default: bool
    externally_routable: bool


class IPAllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pool_id: UUID
    vps_instance_id: UUID
    address: str
    status: str
    allocation_source: str
    allocated_at: datetime | None
    released_at: datetime | None


class PublicGatewayCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=80)
    public_ip: str = Field(min_length=1, max_length=64)
    provider: str = Field(default="", max_length=80)
    region: str = Field(default="pk-local", max_length=80)
    gateway_type: str = Field(default="mikrotik", max_length=40)


class PublicGatewayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    public_ip: str
    provider: str
    region: str
    gateway_type: str
    is_active: bool


class PortMappingCreate(BaseModel):
    gateway_id: UUID
    protocol: str = "tcp"
    private_port: int = Field(ge=1, le=65535)
    public_port: int | None = Field(default=None, ge=1, le=65535)


class PortMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gateway_id: UUID
    vps_instance_id: UUID
    organization_id: UUID
    protocol: str
    public_port: int
    private_ip: str
    private_port: int
    status: str
    allocation_source: str
    allocated_at: datetime | None
    released_at: datetime | None


class VPSNetworkRead(BaseModel):
    primary_ip: str
    private_addresses: list[str]
    public_addresses: list[str]
    network_status: str
