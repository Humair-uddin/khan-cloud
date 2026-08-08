from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.user import User
from app.schemas.compute import ComputeHostRead, VPSAction, VPSCreate, VPSRead
from app.services.compute_service import (
    ComputeError, create_vps, get_visible_vps, list_compute_hosts, queue_vps_action, visible_vps,
)

router = APIRouter(prefix="/compute", tags=["compute"])


@router.get("/hosts", response_model=list[ComputeHostRead])
def hosts(
    user: User = Depends(require_permission("compute.hosts.read")),
    db: Session = Depends(get_db),
):
    return list_compute_hosts(db)


@router.get("/vps", response_model=list[VPSRead])
def list_vps(
    user: User = Depends(require_permission("vps.read")),
    db: Session = Depends(get_db),
):
    return visible_vps(db, user)


@router.post("/vps", response_model=VPSRead, status_code=status.HTTP_201_CREATED)
def provision_vps(
    payload: VPSCreate,
    user: User = Depends(require_permission("vps.manage")),
    db: Session = Depends(get_db),
):
    try:
        return create_vps(db, payload=payload, actor=user)
    except ComputeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/vps/{vps_id}", response_model=VPSRead)
def get_vps(
    vps_id: UUID,
    user: User = Depends(require_permission("vps.read")),
    db: Session = Depends(get_db),
):
    try:
        return get_visible_vps(db, user, vps_id)
    except ComputeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/vps/{vps_id}/actions", response_model=VPSRead)
def vps_action(
    vps_id: UUID,
    payload: VPSAction,
    user: User = Depends(require_permission("vps.manage")),
    db: Session = Depends(get_db),
):
    try:
        vps = get_visible_vps(db, user, vps_id)
        return queue_vps_action(db, vps=vps, action=payload.action, actor=user)
    except ComputeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
