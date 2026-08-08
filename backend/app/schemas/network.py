from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


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


class VPSNetworkRead(BaseModel):
    primary_ip: str
    private_addresses: list[str]
    public_addresses: list[str]
    network_status: str
