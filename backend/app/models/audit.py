from typing import Any
from uuid import UUID
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class AuditEvent(BaseModel):
    __tablename__ = "audit_events"
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(150), index=True)
    resource_type: Mapped[str] = mapped_column(String(100), index=True)
    resource_id: Mapped[str] = mapped_column(String(255), index=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    result: Mapped[str] = mapped_column(String(30), default="success", index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
