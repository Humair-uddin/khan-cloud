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
from app.schemas.node import NodeActionRequest,NodeHeartbeatRequest,NodeRead,NodeRegistrationRequest,NodeRegistrationResponse
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
            commit=profile is None,
        )
        if profile is not None:
            consume_profile_code(db, profile, commit=False)
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
    )

@router.post("/heartbeat",response_model=NodeRead)
def heartbeat(payload: NodeHeartbeatRequest,node: Node=Depends(get_authenticated_node),db: Session=Depends(get_db)):
    try: return heartbeat_node(db,node,payload)
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
