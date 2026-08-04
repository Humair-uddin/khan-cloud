from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.user import User
from app.schemas.rbac import (
    CurrentAccess,
    RoleCreate,
    RoleRead,
    UserRoleAssignment,
)
from app.services.rbac_service import (
    RBACConflictError,
    RBACNotFoundError,
    assign_role,
    create_role,
    get_permission_codes,
    get_role_names,
    list_roles,
)

router = APIRouter(prefix="/rbac", tags=["rbac"])


@router.get("/me", response_model=CurrentAccess)
def current_access(user: User = Depends(get_current_user)) -> CurrentAccess:
    return CurrentAccess(
        roles=get_role_names(user),
        permissions=sorted(get_permission_codes(user)),
        is_superuser=user.is_superuser,
    )


@router.get(
    "/roles",
    response_model=list[RoleRead],
    dependencies=[Depends(require_permission("roles.read"))],
)
def roles(db: Session = Depends(get_db)):
    return list_roles(db)


@router.post(
    "/roles",
    response_model=RoleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("roles.manage"))],
)
def add_role(payload: RoleCreate, db: Session = Depends(get_db)):
    try:
        return create_role(
            db,
            payload.name,
            payload.description,
            payload.permissions,
        )
    except RBACConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RBACNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/users/{user_id}/roles",
    response_model=CurrentAccess,
    dependencies=[Depends(require_permission("roles.manage"))],
)
def add_user_role(
    user_id: UUID,
    payload: UserRoleAssignment,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        assign_role(db, user, payload.role_name)
    except RBACNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return CurrentAccess(
        roles=get_role_names(user),
        permissions=sorted(get_permission_codes(user)),
        is_superuser=user.is_superuser,
    )
