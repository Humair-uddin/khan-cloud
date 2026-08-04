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
    NodeHeartbeatRequest,
    NodeRead,
    NodeRegistrationRequest,
    NodeRegistrationResponse,
)
from app.services.node_service import heartbeat_node, register_node

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.post(
    "/register",
    response_model=NodeRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: NodeRegistrationRequest,
    x_enrollment_token: str = Header(alias="X-Enrollment-Token"),
    db: Session = Depends(get_db),
) -> NodeRegistrationResponse:
    if x_enrollment_token != settings.NODE_ENROLLMENT_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid enrollment token.",
        )

    node, node_secret = register_node(db, payload)
    return NodeRegistrationResponse(
        node_id=node.id,
        node_secret=node_secret,
        status=node.status,
    )


@router.post("/heartbeat", response_model=NodeRead)
def heartbeat(
    payload: NodeHeartbeatRequest,
    node: Node = Depends(get_authenticated_node),
    db: Session = Depends(get_db),
) -> Node:
    return heartbeat_node(db, node, payload)


@router.get(
    "",
    response_model=list[NodeRead],
    dependencies=[Depends(require_permission("nodes.read"))],
)
def list_nodes(db: Session = Depends(get_db)):
    return list(db.scalars(select(Node).order_by(Node.name)).unique())


@router.get(
    "/{node_id}",
    response_model=NodeRead,
    dependencies=[Depends(require_permission("nodes.read"))],
)
def get_node(node_id: UUID, db: Session = Depends(get_db)):
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found.")
    return node
