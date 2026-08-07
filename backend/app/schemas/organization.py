from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str
    created_by_user_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrganizationMembershipCreate(BaseModel):
    user_id: UUID
    role: str = Field(default="member", pattern=r"^(owner|admin|member)$")


class OrganizationMembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: str
    created_at: datetime
