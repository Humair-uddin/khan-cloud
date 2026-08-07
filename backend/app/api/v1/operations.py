from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.user import User
from app.schemas.operations_dashboard import OperationsDashboard
from app.services.operations_dashboard_service import build_operations_dashboard

router = APIRouter(prefix="/operations", tags=["operations"])


@router.get("/dashboard", response_model=OperationsDashboard)
def operations_dashboard(
    stale_after_seconds: int = 300,
    user: User = Depends(require_permission("deployments.read")),
    db: Session = Depends(get_db),
):
    try:
        return build_operations_dashboard(
            db,
            user,
            stale_after_seconds=stale_after_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
