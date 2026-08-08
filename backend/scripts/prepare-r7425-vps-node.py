#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.deployment_profile import DeploymentProfile
from app.models.organization import Organization, OrganizationMembership
from app.models.user import User
from app.schemas.deployment_profile import DeploymentProfileCreate
from app.services.deployment_profile_service import (
    create_profile,
    rotate_profile_code,
)
from app.services.organization_service import create_organization


ORG_NAME = "Khan Cloud Infrastructure"
ORG_SLUG = "khan-cloud-infrastructure"
PROFILE_NAME = "R7425 VPS Infrastructure"
NODE_NAME = "KC-R7425-VPS-01"
CONTROL_PLANE_URL = "http://192.168.18.100:8000"
OUTPUT = Path("/tmp/khan-cloud-r7425-vps-node-install.zip")
RUN_OUTPUT = Path("/tmp/khan-cloud-r7425-vps-node-install.run")


def find_actor(db, username: str) -> User:
    actor = db.scalar(select(User).where(User.username == username))
    if actor is None:
        actor = db.scalar(select(User).where(User.email == username))
    if actor is None or not actor.is_active:
        raise RuntimeError(f"Active Control Plane user not found: {username}")
    return actor


def ensure_org(db, actor: User) -> Organization:
    org = db.scalar(select(Organization).where(Organization.slug == ORG_SLUG))
    if org is None:
        return create_organization(
            db,
            name=ORG_NAME,
            slug=ORG_SLUG,
            actor=actor,
        )

    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org.id,
            OrganizationMembership.user_id == actor.id,
        )
    )
    if membership is None:
        db.add(
            OrganizationMembership(
                organization_id=org.id,
                user_id=actor.id,
                role="owner",
            )
        )
        db.commit()
    return org


def ensure_profile(db, actor: User, org: Organization) -> tuple[DeploymentProfile, str]:
    expires_at = datetime.now(UTC) + timedelta(hours=24)

    profile = db.scalar(
        select(DeploymentProfile).where(
            DeploymentProfile.name == PROFILE_NAME,
            DeploymentProfile.organization_id == org.id,
        )
    )

    if profile is None:
        return create_profile(
            db,
            DeploymentProfileCreate(
                name=PROFILE_NAME,
                purpose="vps_infrastructure",
                ownership_type="khan_cloud",
                visibility="internal_only",
                control_plane_url=CONTROL_PLANE_URL,
                allowed_services={
                    "vps": True,
                    "docker": True,
                    "gpu_compute": False,
                },
                resource_policy={
                    "role": "general_compute",
                    "gpu_required": False,
                },
                expires_at=expires_at,
                max_uses=1,
                organization_id=org.id,
            ),
            actor.id,
        )

    profile.purpose = "vps_infrastructure"
    profile.ownership_type = "khan_cloud"
    profile.visibility = "internal_only"
    profile.control_plane_url = CONTROL_PLANE_URL
    profile.allowed_services = {
        "vps": True,
        "docker": True,
        "gpu_compute": False,
    }
    profile.resource_policy = {
        "role": "general_compute",
        "gpu_required": False,
    }
    profile.expires_at = expires_at
    profile.max_uses = 1
    profile.is_active = True
    db.commit()
    code = rotate_profile_code(db, profile, actor.id)
    db.refresh(profile)
    return profile, code


def build_node_bundle(enrollment_code: str) -> None:
    source_root = Path("/opt/khan-cloud/source/node-agent")
    if not source_root.is_dir():
        raise RuntimeError(f"Node Agent source missing: {source_root}")

    with tempfile.TemporaryDirectory(prefix="khan-r7425-") as temp:
        stage = Path(temp) / "khan-cloud-r7425-vps-node-install"
        agent = stage / "agent"

        shutil.copytree(
            source_root,
            agent,
            ignore=shutil.ignore_patterns(
                ".venv",
                ".pytest_cache",
                "__pycache__",
                "*.pyc",
                "*.pyo",
            ),
        )

        config = {
            "agent": {
                "node_name": NODE_NAME,
                "control_plane_url": CONTROL_PLANE_URL,
                "heartbeat_interval_seconds": 30,
                "request_timeout_seconds": 10,
                "log_level": "INFO",
                "state_directory": "/var/lib/khan-cloud-agent",
                "plugin_directory": "/etc/khan-cloud-agent/plugins",
                "observation_only": True,
            },
            "security": {
                "deployment_enrollment_code": enrollment_code,
                "enrollment_token": "",
                "verify_tls": False,
            },
            "enrollment": {
                "endpoint": "/api/v1/nodes/register",
            },
            "heartbeat": {
                "enabled": True,
                "endpoint": "/api/v1/nodes/heartbeat",
            },
            "telemetry": {
                "enabled": True,
                "endpoint": "/api/v1/nodes/installation-events",
                "installer_database_path": "/opt/khan-cloud/state/installer/installer.db",
            },
        }
        (stage / "config.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False)
        )

        install = stage / "install.sh"
        install.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sudo "$HERE/agent/deploy/install-runtime.sh" "$HERE/agent" "$HERE/config.yaml"
"""
        )
        install.chmod(0o700)

        (stage / "README.txt").write_text(
            """Khan Cloud R7425 VPS Node Installer

Target:
  Dell R7425 / Ubuntu 24
  Node name: KC-R7425-VPS-01
  Role: vps_infrastructure / general compute

Run:
  chmod +x install.sh
  ./install.sh

The one-time deployment enrollment code is removed from the installed
configuration immediately after successful enrollment.
"""
        )

        if OUTPUT.exists():
            OUTPUT.unlink()
        with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in stage.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(stage.parent))

        if RUN_OUTPUT.exists():
            RUN_OUTPUT.unlink()
        builder = source_root / "deploy" / "build-universal-run.py"
        bootstrap = source_root / "deploy" / "universal-bootstrap.sh"
        import subprocess
        subprocess.run(
            [
                "python3",
                str(builder),
                "--bootstrap",
                str(bootstrap),
                "--payload",
                str(stage),
                "--output",
                str(RUN_OUTPUT),
            ],
            check=True,
        )

    OUTPUT.chmod(0o600)
    RUN_OUTPUT.chmod(0o700)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="humair-uddin")
    args = parser.parse_args()

    with SessionLocal() as db:
        actor = find_actor(db, args.user)
        org = ensure_org(db, actor)
        profile, code = ensure_profile(db, actor, org)
        organization_id = org.id
        profile_id = profile.id
        expires_at = profile.expires_at

    build_node_bundle(code)

    print("===== R7425 VPS DEPLOYMENT PREPARED =====")
    print("organization_id:", organization_id)
    print("deployment_profile_id:", profile_id)
    print("deployment:", PROFILE_NAME)
    print("purpose: vps_infrastructure")
    print("ownership: khan_cloud")
    print("visibility: internal_only")
    print("enrollment_uses: 1")
    print("enrollment_expires_at:", expires_at)
    print("legacy_node_bundle:", OUTPUT)
    print("universal_node_installer:", RUN_OUTPUT)
    print("universal_node_installer_mode: 0700")
    print("enrollment_code: [HIDDEN INSIDE NODE INSTALLER]")


if __name__ == "__main__":
    main()
