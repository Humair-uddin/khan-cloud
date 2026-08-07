from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class DeploymentProfileCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    purpose: str = Field(
        pattern=r"^(gaming_host|gpu_compute|vps_infrastructure|organization_private|internal_lab)$"
    )
    ownership_type: str = Field(
        pattern=r"^(khan_cloud|trusted_partner|organization|third_party_provider)$"
    )
    visibility: str = Field(
        pattern=r"^(public_marketplace|organization_only|internal_only)$"
    )
    control_plane_url: HttpUrl
    allowed_services: dict[str, Any] = Field(default_factory=dict)
    resource_policy: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    max_uses: int = Field(default=1, ge=1, le=10000)
    organization_id: UUID | None = None


class DeploymentProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    purpose: str
    ownership_type: str
    visibility: str
    control_plane_url: str
    allowed_services: dict[str, Any]
    resource_policy: dict[str, Any]
    enrollment_code_prefix: str
    expires_at: datetime | None
    max_uses: int
    uses_count: int
    is_active: bool
    organization_id: UUID | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class DeploymentProfileCreateResponse(BaseModel):
    profile: DeploymentProfileRead
    enrollment_code: str


class DeploymentProfileResolveRequest(BaseModel):
    enrollment_code: str = Field(min_length=16, max_length=200)


class DeploymentProfileBootstrap(BaseModel):
    profile_id: UUID
    purpose: str
    ownership_type: str
    visibility: str
    control_plane_url: str
    allowed_services: dict[str, Any]
    resource_policy: dict[str, Any]


class DeploymentProfileRotateResponse(BaseModel):
    profile_id: UUID
    enrollment_code: str
