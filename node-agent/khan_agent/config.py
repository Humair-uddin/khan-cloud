from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl


class AgentConfig(BaseModel):
    node_name: str = Field(min_length=1, max_length=128)
    control_plane_url: HttpUrl
    heartbeat_interval_seconds: int = Field(default=30, ge=5, le=3600)
    request_timeout_seconds: int = Field(default=10, ge=1, le=120)
    log_level: str = "INFO"
    state_directory: Path = Path("/var/lib/khan-cloud-agent")
    plugin_directory: Path = Path("/etc/khan-cloud-agent/plugins")
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
    virtualization: VirtualizationConfig = VirtualizationConfig()

    @classmethod
    def load(cls, path: Path) -> "AgentSettings":
        if path.exists():
            raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
            return cls.model_validate(raw)

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
