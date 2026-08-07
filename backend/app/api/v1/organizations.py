from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.user import User
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationMembershipCreate,
    OrganizationMembershipRead,
    OrganizationRead,
)
from app.services.organization_service import (
    OrganizationError,
    add_member,
    create_organization,
    visible_organizations,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_org(
    payload: OrganizationCreate,
    user: User = Depends(require_permission("organizations.manage")),
    db: Session = Depends(get_db),
):
    try:
        return create_organization(db, name=payload.name, slug=payload.slug, actor=user)
    except OrganizationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[OrganizationRead])
def list_orgs(
    user: User = Depends(require_permission("organizations.read")),
    db: Session = Depends(get_db),
):
    return visible_organizations(db, user)


@router.post("/{organization_id}/members", response_model=OrganizationMembershipRead)
def update_org_member(
    organization_id: UUID,
    payload: OrganizationMembershipCreate,
    user: User = Depends(require_permission("organizations.manage")),
    db: Session = Depends(get_db),
):
    try:
        return add_member(
            db,
            organization_id=organization_id,
            user_id=payload.user_id,
            role=payload.role,
            actor=user,
        )
    except OrganizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
