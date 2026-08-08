from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.portal import PortalSummaryRead
from app.services.portal_service import customer_portal_summary

router = APIRouter(prefix="/portal", tags=["customer-portal"])


@router.get("/summary", response_model=PortalSummaryRead)
def summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return customer_portal_summary(db, user)
