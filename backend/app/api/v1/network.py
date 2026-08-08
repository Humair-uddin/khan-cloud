from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.user import User
from app.schemas.network import NetworkPoolRead, VPSNetworkRead
from app.services.compute_service import ComputeError, get_visible_vps
from app.services.network_service import NetworkError, list_network_pools, visible_vps_network

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/pools", response_model=list[NetworkPoolRead])
def pools(
    user: User = Depends(require_permission("network.pools.read")),
    db: Session = Depends(get_db),
):
    return list_network_pools(db, active_only=False)


@router.get("/vps/{vps_id}", response_model=VPSNetworkRead)
def vps_network(
    vps_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        vps = get_visible_vps(db, user, vps_id)
        return visible_vps_network(db, user=user, vps=vps)
    except (ComputeError, NetworkError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
