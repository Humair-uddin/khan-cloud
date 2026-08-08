from __future__ import annotations

import hashlib
import secrets
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node_installer_artifact import NodeInstallerArtifact
from app.models.user import User
from app.schemas.deployment_profile import DeploymentProfileCreate
from app.schemas.provider_onboarding import NodeInstallerCreate
from app.services.audit_service import record_audit_event
from app.services.deployment_profile_service import create_profile
from app.services.organization_service import user_can_access_organization
from app.services.rbac_service import get_role_names


STATE_ROOT = Path("/var/lib/khan-cloud-control-plane/installers")
AGENT_SOURCE = Path("/opt/khan-cloud/source/node-agent")
STAFF_ROLES = {"platform_owner", "platform_admin", "operator"}


class ProviderOnboardingError(ValueError):
    pass


def hash_download_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _profile_settings_for_role(user: User, role: str) -> dict:
    staff = bool(user.is_superuser or STAFF_ROLES.intersection(get_role_names(user)))
    if role == "vps_host":
        if not staff:
            raise ProviderOnboardingError(
                "VPS infrastructure onboarding is restricted to Khan Cloud operators."
            )
        return {
            "purpose": "vps_infrastructure",
            "ownership_type": "khan_cloud",
            "visibility": "internal_only",
            "allowed_services": {"vps": True, "docker": True, "gpu_compute": False},
            "resource_policy": {
                "role": "general_compute",
                "gpu_required": False,
                "auto_approve_node": True,
            },
        }
    if role == "gpu_host":
        return {
            "purpose": "gpu_compute",
            "ownership_type": "khan_cloud" if staff else "organization",
            "visibility": "internal_only" if staff else "organization_only",
            "allowed_services": {"gpu_compute": True, "docker": True},
            "resource_policy": {
                "role": "gpu_compute",
                "gpu_required": True,
                "auto_approve_node": True,
            },
        }
    if role == "private_compute":
        return {
            "purpose": "organization_private",
            "ownership_type": "organization",
            "visibility": "organization_only",
            "allowed_services": {"private_compute": True, "docker": True},
            "resource_policy": {
                "role": "private_compute",
                "gpu_required": False,
                "auto_approve_node": True,
            },
        }
    raise ProviderOnboardingError(f"Unsupported node role: {role}")


def _build_installer_run(
    *,
    enrollment_code: str,
    node_name: str,
    control_plane_url: str,
    verify_tls: bool,
    output: Path,
) -> None:
    if not AGENT_SOURCE.is_dir():
        raise ProviderOnboardingError("Khan Cloud Node Agent source is unavailable.")
    builder = AGENT_SOURCE / "deploy" / "build-universal-run.py"
    bootstrap = AGENT_SOURCE / "deploy" / "universal-bootstrap.sh"
    if not builder.is_file() or not bootstrap.is_file():
        raise ProviderOnboardingError("Universal bootstrap components are unavailable.")

    with tempfile.TemporaryDirectory(prefix="khan-cloud-provider-") as temp:
        stage = Path(temp) / "payload"
        agent = stage / "agent"
        shutil.copytree(
            AGENT_SOURCE,
            agent,
            ignore=shutil.ignore_patterns(
                ".venv", ".pytest_cache", "__pycache__", "*.pyc", "*.pyo"
            ),
        )
        config = {
            "agent": {
                "node_name": node_name,
                "control_plane_url": control_plane_url,
                "heartbeat_interval_seconds": 30,
                "request_timeout_seconds": 15,
                "log_level": "INFO",
                "state_directory": "/var/lib/khan-cloud-agent",
                "plugin_directory": "/etc/khan-cloud-agent/plugins",
                "observation_only": True,
            },
            "security": {
                "deployment_enrollment_code": enrollment_code,
                "enrollment_token": "",
                "verify_tls": verify_tls,
            },
            "enrollment": {"endpoint": "/api/v1/nodes/register"},
            "heartbeat": {"enabled": True, "endpoint": "/api/v1/nodes/heartbeat"},
            "telemetry": {
                "enabled": True,
                "endpoint": "/api/v1/nodes/installation-events",
                "installer_database_path": "/opt/khan-cloud/state/installer/installer.db",
            },
        }
        (stage / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
        install = stage / "install.sh"
        install.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "HERE=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")\" && pwd)\"\n"
            "\"$HERE/agent/deploy/install-runtime.sh\" \"$HERE/agent\" \"$HERE/config.yaml\"\n"
        )
        install.chmod(0o700)
        subprocess.run(
            [
                "python3", str(builder),
                "--bootstrap", str(bootstrap),
                "--payload", str(stage),
                "--output", str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    output.chmod(0o600)


def create_node_installer(
    db: Session,
    *,
    payload: NodeInstallerCreate,
    actor: User,
    control_plane_url: str,
) -> tuple[NodeInstallerArtifact, str, datetime | None]:
    if not user_can_access_organization(db, actor, payload.organization_id):
        raise ProviderOnboardingError("Organization access denied.")

    settings = _profile_settings_for_role(actor, payload.node_role)
    base_url = control_plane_url.rstrip("/")
    enrollment_expires_at = datetime.now(UTC) + timedelta(hours=24)
    profile, enrollment_code = create_profile(
        db,
        DeploymentProfileCreate(
            name=f"{payload.node_name} onboarding",
            control_plane_url=base_url,
            expires_at=enrollment_expires_at,
            max_uses=1,
            organization_id=payload.organization_id,
            **settings,
        ),
        actor.id,
    )

    artifact_id = secrets.token_hex(16)
    filename = f"khan-cloud-node-{payload.node_name.lower()}.run"
    artifact_dir = STATE_ROOT / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    artifact_dir.chmod(0o700)
    artifact_path = artifact_dir / filename

    try:
        _build_installer_run(
            enrollment_code=enrollment_code,
            node_name=payload.node_name,
            control_plane_url=base_url,
            verify_tls=base_url.startswith("https://"),
            output=artifact_path,
        )
    except Exception:
        shutil.rmtree(artifact_dir, ignore_errors=True)
        profile.is_active = False
        db.commit()
        raise

    token = "kcinst_" + secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=payload.download_expires_minutes)
    artifact = NodeInstallerArtifact(
        deployment_profile_id=profile.id,
        organization_id=payload.organization_id,
        created_by_user_id=actor.id,
        node_name=payload.node_name,
        node_role=payload.node_role,
        filename=filename,
        artifact_path=str(artifact_path),
        download_token_hash=hash_download_token(token),
        download_token_prefix=token[:12],
        expires_at=expires_at,
        download_count=0,
        max_downloads=5,
    )
    db.add(artifact)
    db.flush()
    record_audit_event(
        db,
        actor_user_id=actor.id,
        action="node_installer.created",
        resource_type="node_installer_artifact",
        resource_id=str(artifact.id),
        details={
            "deployment_profile_id": str(profile.id),
            "organization_id": str(payload.organization_id),
            "node_name": payload.node_name,
            "node_role": payload.node_role,
        },
    )
    db.commit()
    db.refresh(artifact)
    return artifact, token, enrollment_expires_at


def resolve_download(db: Session, token: str) -> NodeInstallerArtifact:
    artifact = db.scalar(
        select(NodeInstallerArtifact).where(
            NodeInstallerArtifact.download_token_hash == hash_download_token(token)
        )
    )
    if artifact is None:
        raise ProviderOnboardingError("Installer download token is invalid.")
    now = datetime.now(UTC)
    expiry = artifact.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if expiry <= now:
        raise ProviderOnboardingError("Installer download link has expired.")
    if artifact.download_count >= artifact.max_downloads:
        raise ProviderOnboardingError("Installer download limit has been reached.")
    path = Path(artifact.artifact_path)
    if not path.is_file():
        raise ProviderOnboardingError("Installer artifact is unavailable.")
    artifact.download_count += 1
    db.commit()
    db.refresh(artifact)
    return artifact
