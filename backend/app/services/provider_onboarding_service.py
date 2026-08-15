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
from app.services.organization_service import user_can_access_organization, visible_organizations
from app.services.rbac_service import get_role_names


STATE_ROOT = Path("/var/lib/khan-cloud-control-plane/installers")
AGENT_SOURCE = Path("/opt/khan-cloud/source/node-agent")
STAFF_ROLES = {"platform_owner", "platform_admin", "operator"}


class ProviderOnboardingError(ValueError):
    pass


def hash_download_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _profile_settings_for_role(
    user: User,
    role: str,
    *,
    target_platform: str = "linux",
) -> dict:
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
    if role == "gaming_host":
        if not staff:
            raise ProviderOnboardingError(
                "Khan Cloud gaming-host onboarding is restricted to Khan Cloud operators."
            )

        # Gaming hosts are intentionally Windows-only until another platform
        # has passed Khan Cloud qualification for the complete gaming stack.
        if target_platform != "windows":
            raise ProviderOnboardingError(
                "Khan Cloud gaming hosts currently require Windows."
            )

        return {
            "purpose": "gaming_host",
            "ownership_type": "khan_cloud",
            "visibility": "internal_only",
            "allowed_services": {
                "gaming": True,
                "streaming": True,
                "vps": False,
                "enterprise_vm": False,
                "gpu_compute": False,
            },
            "resource_policy": {
                "role": "gaming_host",

                # Platform qualification is policy, not an installer guess.
                "supported_platforms": ["windows"],

                # Keep the existing compatibility field while moving hardware
                # qualification into an explicit policy object.
                "gpu_required": True,
                "gpu_policy": {
                    "required": True,

                    # Gaming admission is based on capabilities rather than
                    # maintaining an ever-growing GPU model allowlist.
                    "qualification_mode": "capability",
                    "vendor": "nvidia",

                    # 8 GiB is Khan Cloud's minimum gaming-host quality floor.
                    "minimum_vram_mb": 8192,

                    # A gaming host must expose a functioning GPU and the
                    # hardware video-encoding capability required by the
                    # streaming stack.
                    "require_operational_gpu": True,
                    "required_capabilities": [
                        "hardware_video_encode",
                    ],

                    # Commercial tiers can evolve independently from the
                    # hard admission floor. Do not infer tier from VRAM alone.
                    "quality_policy": {
                        "baseline": {
                            "minimum_vram_mb": 8192,
                        },
                        "grading": "capability_and_performance",
                    },

                    # Retained only for backward-compatible manifests.
                    "approved_models": [],
                },

                "driver_policy": {
                    "vendor": "nvidia",
                    "required": True,

                    # Customer/provider machines already have a working GPU
                    # driver. Khan Cloud validates it but does not replace or
                    # upgrade it during normal onboarding.
                    "management": "preserve_existing",
                    "require_operational": True,
                    "automatic_upgrade": False,

                    # Legacy policy fields remain representable but are not
                    # used to force an arbitrary version during onboarding.
                    "minimum_version": None,
                    "approved_branches": [],
                },

                "workload_policy": {
                    "primary": ["gaming"],
                    "optional_interruptible": [
                        "ai",
                        "rendering",
                        "editing",
                    ],
                },

                "execution_backend": "windows_native",
                "streaming_backend": "sunshine",
                "backend_policy": "profile_defined",
                "auto_approve_node": True,
            },
        }

    raise ProviderOnboardingError(f"Unsupported node role: {role}")


def _build_installer_manifest(
    *,
    node_role: str,
    target_platform: str,
    settings: dict,
) -> dict:
    resource_policy = settings.get("resource_policy", {})

    gpu_policy = resource_policy.get("gpu_policy", {})
    driver_policy = resource_policy.get("driver_policy", {})
    workload_policy = resource_policy.get("workload_policy", {})

    feature_pack_ids = {
        ("gaming_host", "windows"): "FP-GAMING-WINDOWS",
    }

    feature_pack_id = feature_pack_ids.get(
        (node_role, target_platform),
        (
            "FP-"
            + node_role.replace("_", "-").upper()
            + "-"
            + target_platform.upper()
        ),
    )

    manifest = {
        "feature_pack": {
            "id": feature_pack_id,
            "name": (
                f"Khan Cloud {node_role.replace('_', ' ').title()} "
                f"({target_platform.title()})"
            ),
            "version": "1.0.0",
        },
        "deployment": {
            "purpose": settings.get("purpose", node_role),
            "platform": target_platform,
            "execution_backend": resource_policy.get(
                "execution_backend"
            ),
            "streaming_backend": resource_policy.get(
                "streaming_backend"
            ),
        },
        "qualification": {
            "gpu": {
                "required": bool(
                    gpu_policy.get(
                        "required",
                        resource_policy.get("gpu_required", False),
                    )
                ),
                "qualification_mode": gpu_policy.get(
                    "qualification_mode",
                    "allowlist",
                ),
                "approved_models": list(
                    gpu_policy.get("approved_models", [])
                ),
                "vendor": gpu_policy.get("vendor"),
                "minimum_vram_mb": gpu_policy.get(
                    "minimum_vram_mb"
                ),
                "required_capabilities": list(
                    gpu_policy.get("required_capabilities", [])
                ),
                "require_operational_gpu": bool(
                    gpu_policy.get(
                        "require_operational_gpu",
                        False,
                    )
                ),
                "quality_policy": dict(
                    gpu_policy.get("quality_policy", {})
                ),
            },
            "driver": {
                "vendor": driver_policy.get("vendor"),
                "required": bool(
                    driver_policy.get("required", False)
                ),
                "management": driver_policy.get(
                    "management",
                    "preserve_existing",
                ),
                "require_operational": bool(
                    driver_policy.get(
                        "require_operational",
                        False,
                    )
                ),
                "automatic_upgrade": bool(
                    driver_policy.get(
                        "automatic_upgrade",
                        False,
                    )
                ),
                "minimum_version": driver_policy.get(
                    "minimum_version"
                ),
                "approved_branches": list(
                    driver_policy.get("approved_branches", [])
                ),
            },
            "workloads": {
                "primary": list(
                    workload_policy.get("primary", [])
                ),
                "optional_interruptible": list(
                    workload_policy.get(
                        "optional_interruptible",
                        [],
                    )
                ),
            },
        },
        "compatibility": {
            "operating_systems": [target_platform],
        },
        "components": {},
    }

    return manifest


def _build_installer_run(
    *,
    enrollment_code: str,
    node_name: str,
    node_role: str,
    gaming_execution_backend: str,
    gaming_streaming_backend: str,
    control_plane_url: str,
    verify_tls: bool,
    output: Path,
    installer_manifest: dict | None = None,
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
                "node_role": node_role,
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
            "gaming": {
                "enabled": node_role == "gaming_host",
                "execution_backend": gaming_execution_backend,
                "streaming_backend": gaming_streaming_backend,
            },
            "heartbeat": {"enabled": True, "endpoint": "/api/v1/nodes/heartbeat"},
            "telemetry": {
                "enabled": True,
                "endpoint": "/api/v1/nodes/installation-events",
                "installer_database_path": "/opt/khan-cloud/state/installer/installer.db",
            },
        }
        (stage / "config.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False)
        )

        if installer_manifest is not None:
            (stage / "installer-manifest.yaml").write_text(
                yaml.safe_dump(
                    installer_manifest,
                    sort_keys=False,
                )
            )

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




def _build_windows_installer(
    *,
    enrollment_code: str,
    node_name: str,
    node_role: str,
    gaming_execution_backend: str,
    gaming_streaming_backend: str,
    control_plane_url: str,
    verify_tls: bool,
    output: Path,
    installer_manifest: dict | None = None,
) -> None:
    if not AGENT_SOURCE.is_dir():
        raise ProviderOnboardingError(
            "Khan Cloud Node Agent source is unavailable."
        )

    windows_installer = AGENT_SOURCE / "deploy" / "install-runtime.ps1"
    windows_bootstrap = AGENT_SOURCE / "deploy" / "universal-bootstrap.ps1"
    if not windows_installer.is_file():
        raise ProviderOnboardingError(
            "Windows runtime installer is unavailable."
        )

    with tempfile.TemporaryDirectory(
        prefix="khan-cloud-provider-windows-"
    ) as temp:
        stage = Path(temp) / "payload"
        agent = stage / "agent"

        shutil.copytree(
            AGENT_SOURCE,
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
                "node_name": node_name,
                "node_role": node_role,
                "control_plane_url": control_plane_url,
                "heartbeat_interval_seconds": 30,
                "request_timeout_seconds": 15,
                "log_level": "INFO",
                "observation_only": True,
            },
            "security": {
                "deployment_enrollment_code": enrollment_code,
                "enrollment_token": "",
                "verify_tls": verify_tls,
            },
            "enrollment": {
                "endpoint": "/api/v1/nodes/register",
            },
            "gaming": {
                "enabled": node_role == "gaming_host",
                "execution_backend": gaming_execution_backend,
                "streaming_backend": gaming_streaming_backend,
            },
            "heartbeat": {
                "enabled": True,
                "endpoint": "/api/v1/nodes/heartbeat",
            },
            "telemetry": {
                "enabled": False,
                "endpoint": "/api/v1/nodes/installation-events",
            },
        }

        (stage / "config.yaml").write_text(
            yaml.safe_dump(config, sort_keys=False)
        )

        if installer_manifest is not None:
            (stage / "installer-manifest.yaml").write_text(
                yaml.safe_dump(
                    installer_manifest,
                    sort_keys=False,
                )
            )

        install_ps1 = stage / "install.ps1"
        install_ps1.write_text(
            '$ErrorActionPreference = "Stop"\n'
            '$Here = Split-Path -Parent $MyInvocation.MyCommand.Path\n'
            '& "$Here\\agent\\deploy\\universal-bootstrap.ps1" '
            '-SourceDir "$Here\\agent" '
            '-ConfigFile "$Here\\config.yaml" -InstallerManifest "$Here\\installer-manifest.yaml"\n'
        )

        archive_base = Path(temp) / "windows-installer"

        shutil.make_archive(
            str(archive_base),
            "zip",
            root_dir=stage,
        )

        generated = archive_base.with_suffix(".zip")

        output.parent.mkdir(parents=True, exist_ok=True)

        if output.exists():
            output.unlink()

        shutil.move(str(generated), str(output))


def create_node_installer(
    db: Session,
    *,
    payload: NodeInstallerCreate,
    actor: User,
    control_plane_url: str,
) -> tuple[NodeInstallerArtifact, str, datetime | None]:
    organization_id = payload.organization_id
    if organization_id is None:
        organizations = visible_organizations(db, actor)
        if len(organizations) != 1:
            raise ProviderOnboardingError(
                "Account ownership could not be inferred automatically."
            )
        organization_id = organizations[0].id
    if not user_can_access_organization(db, actor, organization_id):
        raise ProviderOnboardingError("Organization access denied.")

    node_name = payload.node_name or ("KC-NODE-" + secrets.token_hex(3).upper())
    settings = _profile_settings_for_role(
        actor,
        payload.node_role,
        target_platform=payload.target_platform,
    )
    base_url = control_plane_url.rstrip("/")
    enrollment_expires_at = datetime.now(UTC) + timedelta(hours=24)
    profile, enrollment_code = create_profile(
        db,
        DeploymentProfileCreate(
            name=f"{node_name} onboarding",
            control_plane_url=base_url,
            expires_at=enrollment_expires_at,
            max_uses=1,
            organization_id=organization_id,
            **settings,
        ),
        actor.id,
    )

    artifact_id = secrets.token_hex(16)

    if payload.target_platform == "windows":
        filename = f"khan-cloud-node-{node_name.lower()}-windows.zip"
    else:
        filename = f"khan-cloud-node-{node_name.lower()}.run"
    artifact_dir = STATE_ROOT / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    artifact_dir.chmod(0o700)
    artifact_path = artifact_dir / filename

    try:
        installer_builder = (
            _build_windows_installer
            if payload.target_platform == "windows"
            else _build_installer_run
        )

        installer_manifest = _build_installer_manifest(
            node_role=payload.node_role,
            target_platform=payload.target_platform,
            settings=settings,
        )

        installer_builder(
            enrollment_code=enrollment_code,
            node_name=node_name,
            node_role=payload.node_role,
            gaming_execution_backend=str(
                settings.get("resource_policy", {}).get(
                    "execution_backend",
                    "none",
                )
            ),
            gaming_streaming_backend=str(
                settings.get("resource_policy", {}).get(
                    "streaming_backend",
                    "none",
                )
            ),
            control_plane_url=base_url,
            verify_tls=base_url.startswith("https://"),
            output=artifact_path,
            installer_manifest=installer_manifest,
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
        organization_id=organization_id,
        created_by_user_id=actor.id,
        node_name=node_name,
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
            "organization_id": str(organization_id),
            "node_name": node_name,
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
