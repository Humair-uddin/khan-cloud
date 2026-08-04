from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.node import Node
from app.services.node_service import authenticate_node


def get_authenticated_node(
    x_node_id: UUID = Header(alias="X-Node-ID"),
    x_node_secret: str = Header(alias="X-Node-Secret"),
    db: Session = Depends(get_db),
) -> Node:
    node = authenticate_node(db, x_node_id, x_node_secret)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node credentials.",
        )
    if not node.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Node is disabled.",
        )
    return node
