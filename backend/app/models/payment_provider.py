from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PaymentProvider(BaseModel):
    __tablename__ = "payment_providers"

    code: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        index=True,
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )
    adapter_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(
        String(20),
        default="sandbox",
        nullable=False,
    )

    capabilities_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    supported_currencies_json: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    credential_reference: Mapped[str] = mapped_column(
        String(240),
        default="",
        nullable=False,
    )
    webhook_secret_reference: Mapped[str] = mapped_column(
        String(240),
        default="",
        nullable=False,
    )

    webhook_tolerance_seconds: Mapped[int] = mapped_column(
        BigInteger,
        default=300,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="configured",
        index=True,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "webhook_tolerance_seconds > 0",
            name="ck_payment_provider_webhook_tolerance_positive",
        ),
    )


class PaymentProviderReference(BaseModel):
    __tablename__ = "payment_provider_references"

    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payment_providers.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    reference_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    provider_reference: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    internal_resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    internal_resource_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        index=True,
        nullable=False,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "reference_type",
            "provider_reference",
            name="uq_payment_provider_external_reference",
        ),
        Index(
            "ix_payment_provider_internal_reference",
            "internal_resource_type",
            "internal_resource_id",
        ),
    )


class PaymentWebhookReceipt(BaseModel):
    __tablename__ = "payment_webhook_receipts"

    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("payment_providers.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    event_id: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(80),
        index=True,
        nullable=False,
    )

    raw_body_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    normalized_payload_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    provider_timestamp: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    signature_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    processing_status: Mapped[str] = mapped_column(
        String(30),
        default="accepted",
        index=True,
        nullable=False,
    )

    reconciliation_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "payment_reconciliation_events.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    result_resource_type: Mapped[str] = mapped_column(
        String(50),
        default="",
        nullable=False,
    )
    result_resource_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )

    error_code: Mapped[str] = mapped_column(
        String(80),
        default="",
        nullable=False,
    )

    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "event_id",
            name="uq_payment_webhook_provider_event",
        ),
        CheckConstraint(
            "provider_timestamp > 0",
            name="ck_payment_webhook_timestamp_positive",
        ),
    )
