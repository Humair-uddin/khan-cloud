from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.deployment_profile import DeploymentProfile
from app.models.user import User
from app.schemas.deployment_profile import (
    DeploymentProfileBootstrap,
    DeploymentProfileCreate,
    DeploymentProfileCreateResponse,
    DeploymentProfileRead,
    DeploymentProfileResolveRequest,
    DeploymentProfileRotateResponse,
)
from app.services.deployment_profile_service import (
    DeploymentProfileError,
    create_profile,
    resolve_profile,
    rotate_profile_code,
)

router = APIRouter(prefix="/deployment-profiles", tags=["deployment-profiles"])


@router.post(
    "",
    response_model=DeploymentProfileCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_profile(
    payload: DeploymentProfileCreate,
    user: User = Depends(require_permission("deployment_profiles.manage")),
    db: Session = Depends(get_db),
):
    try:
        profile, code = create_profile(db, payload, user.id)
    except DeploymentProfileError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return DeploymentProfileCreateResponse(profile=profile, enrollment_code=code)


@router.get("", response_model=list[DeploymentProfileRead])
def list_profiles(
    user: User = Depends(require_permission("deployment_profiles.read")),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(DeploymentProfile).order_by(DeploymentProfile.created_at.desc())
        ).unique()
    )


@router.get("/{profile_id}", response_model=DeploymentProfileRead)
def get_profile(
    profile_id: UUID,
    user: User = Depends(require_permission("deployment_profiles.read")),
    db: Session = Depends(get_db),
):
    profile = db.get(DeploymentProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Deployment profile not found.")
    return profile


@router.post(
    "/{profile_id}/rotate-code",
    response_model=DeploymentProfileRotateResponse,
)
def rotate_code(
    profile_id: UUID,
    user: User = Depends(require_permission("deployment_profiles.manage")),
    db: Session = Depends(get_db),
):
    profile = db.get(DeploymentProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Deployment profile not found.")
    code = rotate_profile_code(db, profile, user.id)
    return DeploymentProfileRotateResponse(
        profile_id=profile.id,
        enrollment_code=code,
    )


@router.post("/resolve", response_model=DeploymentProfileBootstrap)
def resolve(
    payload: DeploymentProfileResolveRequest,
    db: Session = Depends(get_db),
):
    try:
        profile = resolve_profile(db, payload.enrollment_code)
    except DeploymentProfileError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return DeploymentProfileBootstrap(
        profile_id=profile.id,
        purpose=profile.purpose,
        ownership_type=profile.ownership_type,
        visibility=profile.visibility,
        control_plane_url=profile.control_plane_url,
        allowed_services=profile.allowed_services,
        resource_policy=profile.resource_policy,
    )
