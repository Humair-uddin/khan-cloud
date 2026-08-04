from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Node(BaseModel):
    __tablename__ = "nodes"

    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    machine_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(String(30), default="online", index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

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
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
