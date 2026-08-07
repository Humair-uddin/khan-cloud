from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.installation_event import InstallationEvent
from app.models.node import Node
from app.schemas.installation_event import InstallationEventCreate


SENSITIVE_KEYS = {
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "node_secret",
    "enrollment_code",
}

_ALLOWED_DETAIL_KEYS = {
    "dry_run",
    "current_stage",
    "installer_version",
    "attempt_number",
    "timed_out",
    "verified",
}

_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+"
)


def sanitize_message(message: str) -> str:
    cleaned = _SECRET_PATTERN.sub(r"\1=[REDACTED]", message or "")
    return cleaned[:500]


def sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in (details or {}).items():
        normalized = str(key).lower()
        if normalized in SENSITIVE_KEYS:
            continue
        if normalized not in _ALLOWED_DETAIL_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[normalized] = value
    return safe


def record_installation_event(
    db: Session,
    *,
    node: Node,
    payload: InstallationEventCreate,
) -> InstallationEvent:
    event = InstallationEvent(
        node_id=node.id,
        deployment_profile_id=node.deployment_profile_id,
        transaction_id=payload.transaction_id,
        feature_pack_id=payload.feature_pack_id,
        feature_pack_version=payload.feature_pack_version,
        status=payload.status,
        stage=payload.stage,
        failure_category=payload.failure_category,
        message=sanitize_message(payload.message),
        details=sanitize_details(payload.details),
        reported_at=payload.reported_at,
    )
    db.add(event)

    node.installation_status = payload.status
    node.installation_stage = payload.stage
    node.installation_failure_category = payload.failure_category
    node.installation_message = sanitize_message(payload.message)
    node.installation_updated_at = payload.reported_at or datetime.now(UTC)

    db.commit()
    db.refresh(event)
    db.refresh(node)
    return event


def list_node_installation_events(
    db: Session,
    node_id,
    *,
    limit: int = 100,
) -> list[InstallationEvent]:
    return list(
        db.scalars(
            select(InstallationEvent)
            .where(InstallationEvent.node_id == node_id)
            .order_by(InstallationEvent.created_at.desc())
            .limit(limit)
        ).all()
    )
