from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class ProvisioningEventCreate(BaseModel):
    deployment_id: str = Field(default="", max_length=128)
    stage: str = Field(default="connected", max_length=60)
    status: str = Field(default="idle", max_length=40)
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    downloaded_bytes: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    bytes_per_second: float = Field(default=0.0, ge=0.0)
    eta_seconds: int | None = Field(default=None, ge=0)
    last_checkpoint: str = Field(default="", max_length=160)
    retry_count: int = Field(default=0, ge=0)
    desired_image_version: str = Field(default="", max_length=100)
    message: str = Field(default="", max_length=500)
    updated_at: float | None = None


class ProvisioningEventRead(ProvisioningEventCreate):
    node_id: str


class DesiredStateRead(BaseModel):
    desired_image_version: str = ""
    provisioning_required: bool = False
    capacity_mode: str = "shared"
    image_build_plan: dict[str, Any] = Field(default_factory=dict)
