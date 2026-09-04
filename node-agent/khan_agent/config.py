from __future__ import annotations

import os
import platform

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl


def _default_state_directory() -> Path:
    if platform.system() == "Windows":
        program_data = Path(os.environ.get("ProgramData", r"C:\\ProgramData"))
        return program_data / "KhanCloud" / "Agent"

    return Path("/var/lib/khan-cloud-agent")


def _default_plugin_directory() -> Path:
    if platform.system() == "Windows":
        return _default_state_directory() / "plugins"

    return Path("/etc/khan-cloud-agent/plugins")


class AgentConfig(BaseModel):
    node_name: str = Field(min_length=1, max_length=128)
    node_role: str = "generic"
    control_plane_url: HttpUrl
    heartbeat_interval_seconds: int = Field(default=30, ge=5, le=3600)
    request_timeout_seconds: int = Field(default=10, ge=1, le=120)
    log_level: str = "INFO"
    state_directory: Path = Field(default_factory=lambda: _default_state_directory())
    plugin_directory: Path = Field(default_factory=lambda: _default_plugin_directory())
    observation_only: bool = True


class SecurityConfig(BaseModel):
    deployment_enrollment_code: str = ""
    # Legacy shared token remains only for backwards-compatible private/lab use.
    enrollment_token: str = ""
    verify_tls: bool = True


class HeartbeatConfig(BaseModel):
    enabled: bool = False
    endpoint: str = "/api/v1/nodes/heartbeat"


class EnrollmentConfig(BaseModel):
    endpoint: str = "/api/v1/nodes/register"


class TelemetryConfig(BaseModel):
    enabled: bool = True
    endpoint: str = "/api/v1/nodes/installation-events"
    installer_database_path: Path = Path("/opt/khan-cloud/state/installer/installer.db")




class ProvisioningConfig(BaseModel):
    enabled: bool = True
    endpoint: str = "/api/v1/nodes/provisioning-events"
    desired_state_endpoint: str = "/api/v1/nodes/desired-state"
    artifact_cache_directory: Path = Field(default_factory=lambda: _default_state_directory() / "artifacts")
    download_chunk_bytes: int = Field(default=4 * 1024 * 1024, ge=262144, le=67108864)
    download_timeout_seconds: int = Field(default=60, ge=5, le=600)
    capacity_mode: str = "shared"
    image_builder_enabled: bool = False
    image_builder_worker_script: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "deploy" / "build-windows-golden-image.ps1")

class GamingConfig(BaseModel):
    enabled: bool = False
    execution_backend: str = "none"
    streaming_backend: str = "none"
    session_broker_mode: str = "existing"
    session_broker_username: str = "KhanGaming"
    sunshine_api_url: str = "https://127.0.0.1:47990"
    sunshine_api_username: str = ""
    sunshine_api_password: str = Field(default="", exclude=True)
    sunshine_credential_source: str = "config"
    sunshine_secret_name: str = "KhanCloudSunshineApiPassword"
    sunshine_verify_tls: bool = False
    vdd_template_path: Path = Path(
        r"C:\ProgramData\KhanCloud\VirtualDisplay\RuntimeConfig\khan-vdd-settings.xml"
    )
    vdd_target_root: Path = Path(
        r"C:\ProgramData\KhanCloud\VirtualDisplay"
    )


class VirtualizationConfig(BaseModel):
    execution_enabled: bool = False
    jobs_endpoint: str = "/api/v1/node-runtime/jobs/next"
    job_result_endpoint_prefix: str = "/api/v1/node-runtime/jobs"
    network_name: str = "kc-vps-net"
    storage_root: Path = Path("/var/lib/khan-cloud/vps")
    base_image_path: Path = Path("/var/lib/khan-cloud/vps/images/ubuntu-24.04-base.qcow2")


class AgentSettings(BaseModel):
    agent: AgentConfig
    security: SecurityConfig = SecurityConfig()
    heartbeat: HeartbeatConfig = HeartbeatConfig()
    enrollment: EnrollmentConfig = EnrollmentConfig()
    telemetry: TelemetryConfig = TelemetryConfig()
    provisioning: ProvisioningConfig = ProvisioningConfig()
    virtualization: VirtualizationConfig = VirtualizationConfig()
    gaming: GamingConfig = GamingConfig()

    @classmethod
    def load(cls, path: Path) -> "AgentSettings":
        if path.exists():
            raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
            settings = cls.model_validate(raw)

            credential_source = (
                settings.gaming.sunshine_credential_source
                .strip()
                .lower()
            )

            if credential_source == "windows_lsa":
                if settings.gaming.sunshine_api_password:
                    raise ValueError(
                        "sunshine_api_password must not contain "
                        "plaintext when sunshine_credential_source "
                        "is windows_lsa."
                    )

                if not settings.gaming.sunshine_api_username.strip():
                    raise ValueError(
                        "sunshine_api_username is required when "
                        "Sunshine uses Windows protected credentials."
                    )

                from khan_agent.windows_protected_secret import (
                    ProtectedSecretError,
                    read_windows_protected_secret,
                )

                try:
                    secret = read_windows_protected_secret(
                        settings.gaming.sunshine_secret_name,
                        required=True,
                    )
                except ProtectedSecretError as exc:
                    raise ValueError(
                        "Unable to load the protected Sunshine "
                        "API credential."
                    ) from exc

                settings.gaming.sunshine_api_password = (
                    secret or ""
                )

            elif credential_source != "config":
                raise ValueError(
                    "Unsupported sunshine_credential_source: "
                    f"{credential_source or '<empty>'}."
                )

            return settings

        return cls.model_validate(
            {
                "agent": {
                    "node_name": "KC-NODE-UNCONFIGURED",
                    "control_plane_url": "http://127.0.0.1:8000",
                    "observation_only": True,
                },
                "heartbeat": {"enabled": False},
            }
        )
