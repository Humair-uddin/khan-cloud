from datetime import datetime
from uuid import UUID
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel

class PhysicalHost(BaseModel):
    __tablename__ = "physical_hosts"
    organization_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    system_uuid: Mapped[str] = mapped_column(String(255), default="", index=True)
    serial_number: Mapped[str] = mapped_column(String(255), default="", index=True)
    manufacturer: Mapped[str] = mapped_column(String(255), default="")
    model: Mapped[str] = mapped_column(String(255), default="")
    trust_state: Mapped[str] = mapped_column(String(30), default="observed", index=True)
    deployment_generation: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
