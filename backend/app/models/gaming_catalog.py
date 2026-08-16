from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class GamingTitle(BaseModel):
    __tablename__ = "gaming_titles"
    __table_args__ = (UniqueConstraint("slug", name="uq_gaming_titles_slug"),)

    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    launcher: Mapped[str] = mapped_column(String(40), nullable=False, default="steam", index=True)
    launcher_app_id: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    platform: Mapped[str] = mapped_column(String(40), nullable=False, default="windows", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    minimum_vram_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    minimum_memory_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=8192)
    minimum_cpu_threads: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    minimum_storage_mb: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    streaming_backend: Mapped[str] = mapped_column(String(40), nullable=False, default="sunshine")
    qualification_policy_version: Mapped[str] = mapped_column(String(40), nullable=False, default="kg001-v1")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class NodeGameInventory(BaseModel):
    __tablename__ = "node_game_inventory"
    __table_args__ = (UniqueConstraint("node_id", "gaming_title_id", name="uq_node_game_inventory_node_title"),)

    node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    gaming_title_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("gaming_titles.id", ondelete="CASCADE"), nullable=False, index=True)
    launcher: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    launcher_app_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    install_state: Mapped[str] = mapped_column(String(30), nullable=False, default="absent", index=True)
    install_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    build_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    manifest_path: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class NodeGameQualification(BaseModel):
    __tablename__ = "node_game_qualifications"
    __table_args__ = (UniqueConstraint("node_id", "gaming_title_id", name="uq_node_game_qualification_node_title"),)

    node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    gaming_title_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("gaming_titles.id", ondelete="CASCADE"), nullable=False, index=True)
    qualified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False, default="kg001-v1", index=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
