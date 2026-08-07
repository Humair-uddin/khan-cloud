from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class Node(BaseModel):
    __tablename__ = "nodes"
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    machine_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", index=True)
    lifecycle_state: Mapped[str] = mapped_column(String(30), default="pending_approval", index=True)
    connectivity_state: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    marketplace_state: Mapped[str] = mapped_column(String(30), default="not_eligible", index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    deployment_profile_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    intended_purpose: Mapped[str] = mapped_column(String(50), default="internal_lab", index=True)
    hostname: Mapped[str] = mapped_column(String(255))
    operating_system: Mapped[str] = mapped_column(String(255), default="")
    kernel_version: Mapped[str] = mapped_column(String(255), default="")
    agent_version: Mapped[str] = mapped_column(String(50), default="0.1.0")
    cpu_model: Mapped[str] = mapped_column(String(255), default="")
    cpu_logical_count: Mapped[int] = mapped_column(Integer, default=0)
    memory_total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    docker_available: Mapped[bool] = mapped_column(Boolean, default=False)
    nvidia_available: Mapped[bool] = mapped_column(Boolean, default=False)
    gpu_count: Mapped[int] = mapped_column(Integer, default=0)
    management_ip: Mapped[str] = mapped_column(String(64), default="")
    production_ip: Mapped[str] = mapped_column(String(64), default="")
    inventory: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    installation_status: Mapped[str] = mapped_column(String(40), default="not_started", index=True)
    installation_stage: Mapped[str] = mapped_column(String(60), default="")
    installation_failure_category: Mapped[str] = mapped_column(String(60), default="", index=True)
    installation_message: Mapped[str] = mapped_column(String(500), default="")
    installation_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
