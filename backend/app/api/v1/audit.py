from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.audit import AuditEvent
from app.schemas.audit import AuditEventRead

router=APIRouter(prefix="/audit",tags=["audit"])

@router.get("",response_model=list[AuditEventRead],
 dependencies=[Depends(require_permission("audit.read"))])
def list_audit_events(db: Session=Depends(get_db)):
    return list(db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(500)).unique())
