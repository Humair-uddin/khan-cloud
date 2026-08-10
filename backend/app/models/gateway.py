from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PublicGateway(BaseModel):
    __tablename__ = "public_gateways"

    __table_args__ = (
        CheckConstraint(
            "ingress_mode IN ('direct', 'upstream_nat')",
            name="ck_public_gateway_ingress_mode",
        ),
    )

    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        unique=True,
        index=True,
    )

    public_ip: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="",
    )

    region: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="pk-local",
        index=True,
    )

    gateway_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="mikrotik",
        index=True,
    )

    ingress_mode: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="direct",
    )

    wan_interface: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )


class PortMapping(BaseModel):
    __tablename__ = "port_mappings"

    __table_args__ = (
        CheckConstraint(
            "protocol IN ('tcp', 'udp')",
            name="ck_port_mapping_protocol",
        ),
        CheckConstraint(
            "public_port BETWEEN 1 AND 65535",
            name="ck_port_mapping_public_port",
        ),
        CheckConstraint(
            "private_port BETWEEN 1 AND 65535",
            name="ck_port_mapping_private_port",
        ),
        CheckConstraint(
            "reconcile_action IN ('apply', 'remove')",
            name="ck_port_mapping_reconcile_action",
        ),
        Index(
            "uq_port_mapping_active_endpoint",
            "gateway_id",
            "protocol",
            "public_port",
            unique=True,
            postgresql_where=text("status <> 'released'"),
        ),
    )

    gateway_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("public_gateways.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    vps_instance_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vps_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    protocol: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="tcp",
        index=True,
    )

    public_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    private_ip: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    private_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="allocated",
        index=True,
    )

    allocation_source: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="control_plane",
    )

    allocated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    reconcile_action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="apply",
    )

    reconcile_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
