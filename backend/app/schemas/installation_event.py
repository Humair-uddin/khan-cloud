from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InstallationEventCreate(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=64)
    feature_pack_id: str = Field(default="", max_length=150)
    feature_pack_version: str = Field(default="", max_length=50)
    status: str = Field(min_length=1, max_length=40)
    stage: str = Field(min_length=1, max_length=60)
    failure_category: str = Field(default="", max_length=60)
    message: str = Field(default="", max_length=2000)
    details: dict[str, Any] = Field(default_factory=dict)
    reported_at: datetime | None = None


class InstallationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_id: UUID
    deployment_profile_id: UUID | None
    transaction_id: str
    feature_pack_id: str
    feature_pack_version: str
    status: str
    stage: str
    failure_category: str
    message: str
    details: dict[str, Any]
    reported_at: datetime | None
    created_at: datetime
