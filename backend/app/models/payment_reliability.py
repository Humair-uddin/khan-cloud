from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PaymentWebhookForensicEvent(BaseModel):
    __tablename__ = "payment_webhook_forensic_events"

    provider_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    signature_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    outcome_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    http_status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    retryable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    error_class: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(provider_code)) > 0",
            name="ck_payment_forensic_provider_nonempty",
        ),
        CheckConstraint(
            "length(trim(event_id)) > 0",
            name="ck_payment_forensic_event_nonempty",
        ),
        CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_payment_forensic_payload_hash",
        ),
        CheckConstraint(
            "http_status >= 100 AND http_status <= 599",
            name="ck_payment_forensic_http_status",
        ),
    )


class PaymentProviderHealthEvent(BaseModel):
    __tablename__ = "payment_provider_health_events"

    provider_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    details_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(provider_code)) > 0",
            name="ck_payment_health_provider_nonempty",
        ),
        CheckConstraint(
            "status IN "
            "('healthy','degraded','unavailable',"
            "'disabled','unknown')",
            name="ck_payment_health_status",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_payment_health_latency",
        ),
    )


class PaymentFinancialOutbox(BaseModel):
    __tablename__ = "payment_financial_outbox"

    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    aggregate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_payment_financial_outbox_idempotency",
        ),
        CheckConstraint(
            "length(trim(event_type)) > 0",
            name="ck_payment_outbox_event_type_nonempty",
        ),
        CheckConstraint(
            "length(trim(aggregate_type)) > 0",
            name="ck_payment_outbox_aggregate_type_nonempty",
        ),
        CheckConstraint(
            "length(trim(aggregate_id)) > 0",
            name="ck_payment_outbox_aggregate_id_nonempty",
        ),
        CheckConstraint(
            "length(trim(idempotency_key)) > 0",
            name="ck_payment_outbox_idempotency_nonempty",
        ),
        CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_payment_outbox_payload_hash",
        ),
        CheckConstraint(
            "status IN "
            "('pending','processing','processed','failed')",
            name="ck_payment_outbox_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_payment_outbox_attempt_count",
        ),
    )
