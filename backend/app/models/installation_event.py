from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class InstallationEvent(BaseModel):
    __tablename__ = "installation_events"

    node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    deployment_profile_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    transaction_id: Mapped[str] = mapped_column(String(64), index=True)
    feature_pack_id: Mapped[str] = mapped_column(String(150), default="")
    feature_pack_version: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(40), index=True)
    stage: Mapped[str] = mapped_column(String(60), index=True)
    failure_category: Mapped[str] = mapped_column(String(60), default="", index=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
