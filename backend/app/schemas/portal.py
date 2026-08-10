from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PortalPublicEndpointRead(BaseModel):
    protocol: str
    public_ip: str
    public_port: int
    private_port: int


class PortalVPSRead(BaseModel):
    id: UUID
    name: str
    image: str
    status: str
    desired_state: str
    vcpu: int
    memory_bytes: int
    disk_bytes: int
    primary_ip: str
    private_addresses: list[str]
    public_addresses: list[str]
    public_endpoints: list[PortalPublicEndpointRead]
    access_username: str
    ssh_public_key_fingerprint: str
    guest_ready_at: datetime | None


class PortalSummaryRead(BaseModel):
    vps_total: int
    vps_running: int
    vps_stopped: int
    vps_provisioning: int
    vps: list[PortalVPSRead]
