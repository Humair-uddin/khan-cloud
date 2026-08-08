from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.rbac_dependencies import require_permission
from app.db.database import get_db
from app.models.user import User
from app.schemas.provider_onboarding import NodeInstallerCreate, NodeInstallerCreated
from app.services.provider_onboarding_service import (
    ProviderOnboardingError,
    create_node_installer,
    resolve_download,
)

router = APIRouter(prefix="/provider", tags=["provider-onboarding"])


@router.post(
    "/node-installers",
    response_model=NodeInstallerCreated,
    status_code=status.HTTP_201_CREATED,
)
def generate_node_installer(
    payload: NodeInstallerCreate,
    request: Request,
    user: User = Depends(require_permission("node_installers.manage")),
    db: Session = Depends(get_db),
):
    try:
        artifact, token, enrollment_expires_at = create_node_installer(
            db,
            payload=payload,
            actor=user,
            control_plane_url=str(request.base_url).rstrip("/"),
        )
    except ProviderOnboardingError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Installer generation failed.") from exc

    download_url = str(request.url_for("download_node_installer", token=token))
    quoted = download_url.replace("'", "%27")
    one_command = (
        f"curl -fL '{quoted}' -o /tmp/khan-cloud-node.run && "
        "chmod +x /tmp/khan-cloud-node.run && sudo /tmp/khan-cloud-node.run"
    )
    return NodeInstallerCreated(
        artifact_id=artifact.id,
        deployment_profile_id=artifact.deployment_profile_id,
        organization_id=artifact.organization_id,
        node_name=artifact.node_name,
        node_role=artifact.node_role,
        filename=artifact.filename,
        expires_at=artifact.expires_at,
        download_url=download_url,
        one_command=one_command,
        enrollment_expires_at=enrollment_expires_at,
    )


@router.get("/bootstrap/{token}", name="download_node_installer")
def download_node_installer(token: str, db: Session = Depends(get_db)):
    try:
        artifact = resolve_download(db, token)
    except ProviderOnboardingError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    return FileResponse(
        artifact.artifact_path,
        filename=artifact.filename,
        media_type="application/octet-stream",
    )
