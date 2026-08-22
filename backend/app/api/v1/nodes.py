from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.node_dependencies import get_authenticated_node
from app.api.rbac_dependencies import require_permission
from app.core.config import settings
from app.db.database import get_db
from app.models.node import Node
from app.models.user import User
from app.schemas.node import (
    NodeActionRequest,
    NodeGamingAvailabilityRequest,
    NodeHeartbeatRequest,
    NodeRead,
    NodeRegistrationRequest,
    NodeRegistrationResponse,
)
from app.services.deployment_profile_service import (
    DeploymentProfileError,
    consume_profile_code,
    resolve_profile,
)
from app.services.node_service import (
    NodeLifecycleError,
    heartbeat_node,
    register_node,
    transition_node,
    auto_approve_enrolled_node,
)

router=APIRouter(prefix="/nodes",tags=["nodes"])

@router.post(
    "/register",
    response_model=NodeRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: NodeRegistrationRequest,
    x_deployment_enrollment_code: str | None = Header(
        default=None,
        alias="X-Deployment-Enrollment-Code",
    ),
    x_enrollment_token: str | None = Header(
        default=None,
        alias="X-Enrollment-Token",
    ),
    db: Session = Depends(get_db),
):
    profile = None

    if x_deployment_enrollment_code:
        try:
            profile = resolve_profile(db, x_deployment_enrollment_code)
        except DeploymentProfileError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
    elif x_enrollment_token != settings.NODE_ENROLLMENT_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Valid deployment enrollment code is required.",
        )

    try:
        node, secret = register_node(
            db,
            payload,
            deployment_profile_id=(profile.id if profile else None),
            intended_purpose=(profile.purpose if profile else None),
            organization_id=(profile.organization_id if profile else None),
            commit=profile is None,
        )
        if profile is not None:
            consume_profile_code(db, profile, commit=False)
            if bool((profile.resource_policy or {}).get("auto_approve_node")):
                auto_approve_enrolled_node(db, node)
            db.commit()
            db.refresh(node)
    except (NodeLifecycleError, DeploymentProfileError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return NodeRegistrationResponse(
        node_id=node.id,
        node_secret=secret,
        status=node.status,
        lifecycle_state=node.lifecycle_state,
        deployment_profile_id=node.deployment_profile_id,
        intended_purpose=node.intended_purpose,
        assigned_name=node.name,
        physical_host_id=node.physical_host_id,
        deployment_generation=node.deployment_generation,
    )

@router.post("/heartbeat",response_model=NodeRead)
def heartbeat(payload: NodeHeartbeatRequest,node: Node=Depends(get_authenticated_node),db: Session=Depends(get_db)):
    try:
        updated = heartbeat_node(db,node,payload)
        from app.services.compute_service import sync_node_capacity
        sync_node_capacity(db, updated)
        from app.services.gaming_catalog_service import reconcile_node_gaming_inventory
        if updated.intended_purpose == "gaming_host":
            reconcile_node_gaming_inventory(db, updated)
            db.commit()
            db.refresh(updated)
        return updated
    except NodeLifecycleError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc

@router.get("",response_model=list[NodeRead],dependencies=[Depends(require_permission("nodes.read"))])
def list_nodes(db: Session=Depends(get_db)):
    return list(db.scalars(select(Node).order_by(Node.name)).unique())

@router.get("/{node_id}",response_model=NodeRead,dependencies=[Depends(require_permission("nodes.read"))])
def get_node(node_id: UUID,db: Session=Depends(get_db)):
    node=db.get(Node,node_id)
    if node is None: raise HTTPException(status_code=404,detail="Node not found.")
    return node

def _transition(node_id: UUID,payload: NodeActionRequest,new_state: str,user: User,db: Session):
    node=db.get(Node,node_id)
    if node is None: raise HTTPException(status_code=404,detail="Node not found.")
    try: return transition_node(db,node=node,new_state=new_state,actor_user_id=user.id,reason=payload.reason)
    except NodeLifecycleError as exc: raise HTTPException(status_code=409,detail=str(exc)) from exc

@router.post("/{node_id}/approve",response_model=NodeRead)
def approve_node(node_id: UUID,payload: NodeActionRequest,user: User=Depends(require_permission("nodes.approve")),db: Session=Depends(get_db)):
    return _transition(node_id,payload,"approved",user,db)

@router.post("/{node_id}/reject",response_model=NodeRead)
def reject_node(node_id: UUID,payload: NodeActionRequest,user: User=Depends(require_permission("nodes.approve")),db: Session=Depends(get_db)):
    return _transition(node_id,payload,"rejected",user,db)

@router.post("/{node_id}/disable",response_model=NodeRead)
def disable_node(node_id: UUID,payload: NodeActionRequest,user: User=Depends(require_permission("nodes.disable")),db: Session=Depends(get_db)):
    return _transition(node_id,payload,"disabled",user,db)

@router.post("/{node_id}/enable",response_model=NodeRead)
def enable_node(node_id: UUID,payload: NodeActionRequest,user: User=Depends(require_permission("nodes.disable")),db: Session=Depends(get_db)):
    return _transition(node_id,payload,"approved",user,db)

@router.post("/{node_id}/maintenance",response_model=NodeRead)
def maintenance_node(node_id: UUID,payload: NodeActionRequest,user: User=Depends(require_permission("nodes.maintenance")),db: Session=Depends(get_db)):
    return _transition(node_id,payload,"maintenance",user,db)

@router.post("/{node_id}/retire",response_model=NodeRead)
def retire_node(node_id: UUID,payload: NodeActionRequest,user: User=Depends(require_permission("nodes.retire")),db: Session=Depends(get_db)):
    return _transition(node_id,payload,"retired",user,db)


@router.post(
    "/{node_id}/gaming-availability",
    response_model=NodeRead,
)
def set_gaming_availability(
    node_id: UUID,
    payload: NodeGamingAvailabilityRequest,
    user: User = Depends(require_permission("gaming.manage")),
    db: Session = Depends(get_db),
):
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")

    if node.intended_purpose != "gaming_host":
        raise HTTPException(
            status_code=409,
            detail="Node is not configured as a gaming host.",
        )

    node.gaming_accepting_work = payload.accepting_work
    db.commit()
    db.refresh(node)
    return node

# Installation telemetry is node-authenticated and intentionally sanitized.
from app.schemas.installation_event import InstallationEventCreate, InstallationEventRead
from app.services.installation_telemetry_service import (
    list_node_installation_events,
    record_installation_event,
)


@router.post("/installation-events", response_model=InstallationEventRead, status_code=status.HTTP_201_CREATED)
def installation_event(
    payload: InstallationEventCreate,
    node: Node = Depends(get_authenticated_node),
    db: Session = Depends(get_db),
):
    return record_installation_event(db, node=node, payload=payload)


@router.get(
    "/{node_id}/installation-events",
    response_model=list[InstallationEventRead],
    dependencies=[Depends(require_permission("nodes.read"))],
)
def installation_events(node_id: UUID, limit: int = 100, db: Session = Depends(get_db)):
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")
    safe_limit = max(1, min(limit, 500))
    return list_node_installation_events(db, node_id, limit=safe_limit)


# KG-008A durable host provisioning telemetry. Reuses the existing Node installation
# summary columns so the operations/dashboard model stays single-owner.
from app.schemas.provisioning import ProvisioningEventCreate, ProvisioningEventRead, DesiredStateRead


@router.post("/provisioning-events", response_model=ProvisioningEventRead)
def provisioning_event(
    payload: ProvisioningEventCreate,
    node: Node = Depends(get_authenticated_node),
    db: Session = Depends(get_db),
):
    from datetime import UTC, datetime
    node.installation_status = payload.status
    node.installation_stage = payload.stage
    node.installation_failure_category = (
        "retryable" if payload.status == "failed_retryable" else
        "manual_action" if payload.status == "failed_manual_action" else ""
    )
    node.installation_message = (payload.message or "")[:500]
    node.installation_updated_at = datetime.now(UTC)
    inventory = dict(node.inventory or {})
    inventory["provisioning"] = payload.model_dump()
    node.inventory = inventory
    db.commit()
    db.refresh(node)
    return ProvisioningEventRead(node_id=str(node.id), **payload.model_dump())


@router.get("/desired-state", response_model=DesiredStateRead)
def desired_state(
    node: Node = Depends(get_authenticated_node),
):
    policy = dict(node.capabilities or {}).get("provisioning_policy", {})
    desired_image_version = str(policy.get("desired_image_version") or "")
    capacity_mode = str(policy.get("capacity_mode") or "shared")
    current = dict(node.inventory or {}).get("provisioning", {})
    current_image = str(current.get("desired_image_version") or "")
    return DesiredStateRead(
        desired_image_version=desired_image_version,
        provisioning_required=bool(desired_image_version and current_image != desired_image_version),
        capacity_mode=capacity_mode,
    )
