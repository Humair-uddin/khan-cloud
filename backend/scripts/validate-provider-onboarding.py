#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

import httpx
from sqlalchemy import delete, select

from app.db.database import SessionLocal
from app.models.deployment_profile import DeploymentProfile
from app.models.node_installer_artifact import NodeInstallerArtifact
from app.models.organization import Organization
from app.models.user import User
from app.schemas.provider_onboarding import NodeInstallerCreate
from app.services.provider_onboarding_service import create_node_installer


BASE_URL = "http://127.0.0.1:8000"
NODE_NAME = "KC-PORTAL-VALIDATION"


def main() -> None:
    artifact_id = None
    profile_id = None
    artifact_path = None
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.username == "humair-uddin"))
        if actor is None:
            raise RuntimeError("Validation actor humair-uddin not found.")
        org = db.scalar(select(Organization).order_by(Organization.created_at).limit(1))
        if org is None:
            raise RuntimeError("No organization exists for provider onboarding validation.")
        artifact, token, _ = create_node_installer(
            db,
            payload=NodeInstallerCreate(
                organization_id=org.id,
                node_name=NODE_NAME,
                node_role="private_compute",
                download_expires_minutes=10,
            ),
            actor=actor,
            control_plane_url=BASE_URL,
        )
        artifact_id = artifact.id
        profile_id = artifact.deployment_profile_id
        artifact_path = Path(artifact.artifact_path)

    try:
        response = httpx.get(
            f"{BASE_URL}/api/v1/provider/bootstrap/{token}",
            timeout=30.0,
        )
        response.raise_for_status()
        if not response.content.startswith(b"#!/usr/bin/env bash"):
            raise RuntimeError("Downloaded provider artifact is not a bootstrap script.")
        if b"__KC_PAYLOAD_BELOW__" not in response.content:
            raise RuntimeError("Downloaded provider artifact has no embedded payload marker.")
        print("provider_installer_http_download: PASS")
        print("downloaded_bytes:", len(response.content))
    finally:
        with SessionLocal() as db:
            if artifact_id is not None:
                db.execute(delete(NodeInstallerArtifact).where(NodeInstallerArtifact.id == artifact_id))
            if profile_id is not None:
                db.execute(delete(DeploymentProfile).where(DeploymentProfile.id == profile_id))
            db.commit()
        if artifact_path is not None:
            shutil.rmtree(artifact_path.parent, ignore_errors=True)
        print("validation_cleanup: complete")


if __name__ == "__main__":
    main()
