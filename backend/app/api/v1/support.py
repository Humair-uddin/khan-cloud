from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.support_case import SupportCase
from app.models.user import User
from app.schemas.support_case import SupportCaseCreate, SupportCaseRead, SupportCaseUpdate
from app.services.support_service import (
    SupportCaseError,
    create_support_case,
    update_support_case,
    visible_support_cases,
)

router = APIRouter(prefix="/support-cases", tags=["support"])


@router.post("", response_model=SupportCaseRead, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: SupportCaseCreate,
    user: User = Depends(require_permission("support.manage")),
    db: Session = Depends(get_db),
):
    try:
        return create_support_case(db, payload, user)
    except SupportCaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[SupportCaseRead])
def list_cases(
    user: User = Depends(require_permission("support.read")),
    db: Session = Depends(get_db),
):
    return visible_support_cases(db, user)


@router.patch("/{case_id}", response_model=SupportCaseRead)
def patch_case(
    case_id: UUID,
    payload: SupportCaseUpdate,
    user: User = Depends(require_permission("support.manage")),
    db: Session = Depends(get_db),
):
    case = db.get(SupportCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Support case not found.")
    try:
        return update_support_case(db, case, payload, user)
    except SupportCaseError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
