from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session
from app.models.audit import AuditEvent

def record_audit_event(
    db: Session,
    *,
    actor_user_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str,
    reason: str = "",
    result: str = "success",
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        reason=reason,
        result=result,
        details=details or {},
    )
    db.add(event)
    db.flush()
    return event
