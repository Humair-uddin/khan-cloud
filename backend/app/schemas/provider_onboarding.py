from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class NodeInstallerCreate(BaseModel):
    organization_id: UUID
    node_name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    node_role: Literal["vps_host", "gpu_host", "private_compute"]
    download_expires_minutes: int = Field(default=60, ge=10, le=1440)


class NodeInstallerCreated(BaseModel):
    artifact_id: UUID
    deployment_profile_id: UUID
    organization_id: UUID
    node_name: str
    node_role: str
    filename: str
    expires_at: datetime
    download_url: str
    one_command: str
    enrollment_expires_at: datetime | None
