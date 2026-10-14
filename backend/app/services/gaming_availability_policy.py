"""Fail-closed gaming billing availability boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

BILLING_HEARTBEAT_GRACE_SECONDS = 60


def utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def availability_boundary(last_seen_at: datetime | None) -> datetime | None:
    if last_seen_at is None:
        return None
    return utc(last_seen_at) + timedelta(
        seconds=BILLING_HEARTBEAT_GRACE_SECONDS
    )


def capped_time(now: datetime, cutoff: datetime | None) -> datetime:
    current = utc(now)
    if cutoff is None:
        return current
    return min(current, utc(cutoff))
