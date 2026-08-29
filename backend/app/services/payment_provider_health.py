from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ProviderHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderHealthObservation:
    provider_code: str
    status: ProviderHealthStatus
    latency_ms: int | None
    details: dict[str, Any]
    observed_at: datetime


def build_health_observation(
    *,
    provider_code: str,
    status: ProviderHealthStatus,
    latency_ms: int | None = None,
    details: dict[str, Any] | None = None,
) -> ProviderHealthObservation:
    provider_code = str(
        provider_code or ""
    ).strip()

    if not provider_code:
        raise ValueError(
            "provider_code is required."
        )

    if latency_ms is not None and latency_ms < 0:
        raise ValueError(
            "latency_ms cannot be negative."
        )

    return ProviderHealthObservation(
        provider_code=provider_code,
        status=status,
        latency_ms=latency_ms,
        details=dict(details or {}),
        observed_at=datetime.now(
            timezone.utc
        ),
    )


def record_provider_health(
    db,
    *,
    provider_code: str,
    status: ProviderHealthStatus,
    latency_ms: int | None = None,
    details: dict[str, Any] | None = None,
):
    from app.models.payment_reliability import (
        PaymentProviderHealthEvent,
    )

    observation = build_health_observation(
        provider_code=provider_code,
        status=status,
        latency_ms=latency_ms,
        details=details,
    )

    row = PaymentProviderHealthEvent(
        provider_code=observation.provider_code,
        status=observation.status.value,
        latency_ms=observation.latency_ms,
        details_json=observation.details,
        observed_at=observation.observed_at,
    )

    db.add(row)
    db.flush()

    return row


def latest_provider_health(
    db,
    *,
    provider_code: str,
):
    from sqlalchemy import select
    from app.models.payment_reliability import (
        PaymentProviderHealthEvent,
    )

    return db.scalar(
        select(PaymentProviderHealthEvent)
        .where(
            PaymentProviderHealthEvent.provider_code
            == provider_code.strip().lower()
        )
        .order_by(
            PaymentProviderHealthEvent.observed_at.desc(),
            PaymentProviderHealthEvent.created_at.desc(),
        )
        .limit(1)
    )
