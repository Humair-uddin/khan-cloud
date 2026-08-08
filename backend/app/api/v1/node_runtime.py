from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.node_dependencies import get_authenticated_node
from app.db.database import get_db
from app.models.node import Node
from app.schemas.compute import NodeJobRead, NodeJobResult
from app.services.compute_service import ComputeError, claim_next_job, finish_job

router = APIRouter(prefix="/node-runtime", tags=["node-runtime"])


@router.get("/jobs/next", response_model=NodeJobRead | None)
def next_job(
    response: Response,
    node: Node = Depends(get_authenticated_node),
    db: Session = Depends(get_db),
):
    job = claim_next_job(db, node)
    if job is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return job


@router.post("/jobs/{job_id}/result", response_model=NodeJobRead)
def job_result(
    job_id: UUID,
    payload: NodeJobResult,
    node: Node = Depends(get_authenticated_node),
    db: Session = Depends(get_db),
):
    try:
        return finish_job(
            db, node=node, job_id=job_id, status=payload.status,
            result=payload.result, error_message=payload.error_message,
        )
    except ComputeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
