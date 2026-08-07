from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DeploymentProfile(BaseModel):
    __tablename__ = "deployment_profiles"

    name: Mapped[str] = mapped_column(String(150), index=True)
    purpose: Mapped[str] = mapped_column(String(50), index=True)
    ownership_type: Mapped[str] = mapped_column(String(50), index=True)
    visibility: Mapped[str] = mapped_column(String(50), index=True)

    control_plane_url: Mapped[str] = mapped_column(String(500))
    allowed_services: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    resource_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    enrollment_code_hash: Mapped[str] = mapped_column(String(64), index=True)
    enrollment_code_prefix: Mapped[str] = mapped_column(String(12), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    uses_count: Mapped[int] = mapped_column(Integer, default=0)

    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
