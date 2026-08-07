from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SupportCaseCreate(BaseModel):
    organization_id: UUID
    deployment_profile_id: UUID
    node_id: UUID | None = None
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|critical)$")
    category: str = Field(min_length=2, max_length=60)
    summary: str = Field(min_length=3, max_length=250)
    sanitized_details: str = Field(default="", max_length=1000)


class SupportCaseUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(open|acknowledged|resolved)$")
    priority: str | None = Field(default=None, pattern=r"^(low|normal|high|critical)$")
    assigned_user_id: UUID | None = None


class SupportCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    deployment_profile_id: UUID
    node_id: UUID | None
    status: str
    priority: str
    category: str
    summary: str
    sanitized_details: str
    created_by_user_id: UUID
    assigned_user_id: UUID | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
