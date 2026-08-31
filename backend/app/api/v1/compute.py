from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.user import User
from app.schemas.compute import (
    GamingConnectionLeaseCreate, GamingConnectionLeaseRead, GamingConnectionLeaseIssue,
    GamingConnectionLeaseEventRequest, GamingConnectionPairRequest, GamingVmBlueprintCreate, GamingVmBlueprintRead,
)
from app.schemas.compute import (ComputeHostRead, GamingSessionAction, GamingSessionCreate, GamingSessionRead, VPSAction, VPSCreate, VPSImageRead, VPSRead)
from app.services.compute_service import (
    ComputeError, create_vps, get_visible_vps, list_compute_hosts, list_vps_images, queue_vps_action, visible_vps,
)

router = APIRouter(prefix="/compute", tags=["compute"])


@router.get("/hosts", response_model=list[ComputeHostRead])
def hosts(
    user: User = Depends(require_permission("compute.hosts.read")),
    db: Session = Depends(get_db),
):
    return list_compute_hosts(db)


@router.get("/images", response_model=list[VPSImageRead])
def images(
    user: User = Depends(require_permission("vps.read")),
):
    return list_vps_images()


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


@router.get("/gaming/sessions", response_model=list[GamingSessionRead])
def list_gaming_sessions(
    user: User = Depends(require_permission("gaming.read")),
    db: Session = Depends(get_db),
):
    from app.services.gaming_service import visible_gaming_sessions
    return visible_gaming_sessions(db, user)


@router.post("/gaming/sessions", response_model=GamingSessionRead, status_code=status.HTTP_201_CREATED)
def provision_gaming_session(
    payload: GamingSessionCreate,
    user: User = Depends(require_permission("gaming.manage")),
    db: Session = Depends(get_db),
):
    from app.services.gaming_service import create_gaming_session
    try:
        return create_gaming_session(db, payload=payload, actor=user)
    except ComputeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/gaming/sessions/{session_id}", response_model=GamingSessionRead)
def get_gaming_session(
    session_id: UUID,
    user: User = Depends(require_permission("gaming.read")),
    db: Session = Depends(get_db),
):
    from app.services.gaming_service import get_visible_gaming_session
    try:
        return get_visible_gaming_session(db, user, session_id)
    except ComputeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/gaming/sessions/{session_id}/actions", response_model=GamingSessionRead)
def gaming_session_action(
    session_id: UUID,
    payload: GamingSessionAction,
    user: User = Depends(require_permission("gaming.manage")),
    db: Session = Depends(get_db),
):
    from app.services.gaming_service import get_visible_gaming_session, queue_gaming_action
    try:
        item = get_visible_gaming_session(db, user, session_id)
        return queue_gaming_action(db, session=item, action=payload.action)
    except ComputeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



@router.post(
    "/gaming/sessions/{session_id}/connection-leases",
    response_model=GamingConnectionLeaseIssue,
    status_code=status.HTTP_201_CREATED,
)
def create_gaming_connection_lease(
    session_id: UUID,
    payload: GamingConnectionLeaseCreate,
    user: User = Depends(
        require_permission("gaming.manage")
    ),
    db: Session = Depends(get_db),
):
    from app.services.gaming_connection_service import (
        create_connection_lease,
    )
    from app.services.gaming_service import (
        get_visible_gaming_session,
    )

    try:
        session = get_visible_gaming_session(
            db,
            user,
            session_id,
        )
        lease, connection_token = create_connection_lease(
            db,
            session=session,
            actor=user,
            pairing_ttl_seconds=payload.pairing_ttl_seconds,
            connection_ttl_seconds=payload.connection_ttl_seconds,
            reconnect_grace_seconds=payload.reconnect_grace_seconds,
        )
        return {"lease": lease, "connection_token": connection_token}
    except ComputeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.get(
    "/gaming/sessions/{session_id}/connection-leases/{lease_id}",
    response_model=GamingConnectionLeaseRead,
)
def get_gaming_connection_lease(
    session_id: UUID,
    lease_id: UUID,
    user: User = Depends(
        require_permission("gaming.read")
    ),
    db: Session = Depends(get_db),
):
    from app.services.gaming_connection_service import (
        get_visible_connection_lease,
    )

    try:
        return get_visible_connection_lease(
            db,
            actor=user,
            session_id=session_id,
            lease_id=lease_id,
        )
    except ComputeError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.post(
    "/gaming/sessions/{session_id}/connection-leases/{lease_id}/pair",
    response_model=GamingConnectionLeaseRead,
)
def pair_gaming_connection(
    session_id: UUID,
    lease_id: UUID,
    payload: GamingConnectionPairRequest,
    user: User = Depends(
        require_permission("gaming.manage")
    ),
    db: Session = Depends(get_db),
):
    from app.services.gaming_connection_service import (
        get_visible_connection_lease,
        queue_pairing,
    )

    try:
        lease = get_visible_connection_lease(
            db,
            actor=user,
            session_id=session_id,
            lease_id=lease_id,
        )
        return queue_pairing(
            db,
            lease=lease,
            pin=payload.pin,
        )
    except ComputeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.post(
    "/gaming/sessions/{session_id}/connection-leases/{lease_id}/events",
    response_model=GamingConnectionLeaseRead,
)
def gaming_connection_event(
    session_id: UUID,
    lease_id: UUID,
    payload: GamingConnectionLeaseEventRequest,
    user: User = Depends(require_permission("gaming.manage")),
    db: Session = Depends(get_db),
):
    from app.services.gaming_connection_service import (
        get_visible_connection_lease, record_connection_event,
    )
    try:
        lease = get_visible_connection_lease(
            db, actor=user, session_id=session_id, lease_id=lease_id
        )
        return record_connection_event(
            db, lease=lease, token=payload.connection_token, event=payload.event
        )
    except ComputeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/gaming/sessions/{session_id}/connection-leases/{lease_id}/revoke",
    response_model=GamingConnectionLeaseRead,
)
def revoke_gaming_connection(
    session_id: UUID,
    lease_id: UUID,
    user: User = Depends(
        require_permission("gaming.manage")
    ),
    db: Session = Depends(get_db),
):
    from app.services.gaming_connection_service import (
        get_visible_connection_lease,
        queue_revocation,
    )

    try:
        lease = get_visible_connection_lease(
            db,
            actor=user,
            session_id=session_id,
            lease_id=lease_id,
        )
        return queue_revocation(
            db,
            lease=lease,
        )
    except ComputeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.get("/gaming/vm-blueprints", response_model=list[GamingVmBlueprintRead])
def list_gaming_vm_blueprints(user: User = Depends(require_permission("gaming.read")), db: Session = Depends(get_db)):
    from sqlalchemy import select
    from app.models.compute import GamingVmBlueprint
    return list(db.scalars(select(GamingVmBlueprint).order_by(GamingVmBlueprint.slug)).unique())

@router.post("/gaming/vm-blueprints", response_model=GamingVmBlueprintRead, status_code=status.HTTP_201_CREATED)
def create_gaming_vm_blueprint(payload: GamingVmBlueprintCreate, user: User = Depends(require_permission("gaming.manage")), db: Session = Depends(get_db)):
    from sqlalchemy import select
    from app.models.compute import GamingVmBlueprint
    existing=db.scalar(select(GamingVmBlueprint).where(GamingVmBlueprint.slug==payload.slug))
    if existing is not None: raise HTTPException(status_code=409, detail="Gaming VM blueprint slug already exists.")
    metadata = payload.metadata_json if isinstance(payload.metadata_json, dict) else {}
    if payload.enabled and metadata.get("template_contract_version") != "kg006-v1":
        raise HTTPException(
            status_code=422,
            detail="Enabled Windows gaming blueprints require template_contract_version=kg006-v1.",
        )
    item=GamingVmBlueprint(**payload.model_dump()); db.add(item); db.commit(); db.refresh(item); return item
