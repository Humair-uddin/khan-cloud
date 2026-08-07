from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class FeaturePackInfo(BaseModel):
    id: str
    name: str
    version: str
    minimum_platform_version: str | None = None
    description: str = ""
    signed: bool = False


class ComponentSpec(BaseModel):
    enabled: bool = False
    source: Path | None = None
    destination: Path | None = None


class ServiceRestartSpec(BaseModel):
    name: str


class OperationsSpec(BaseModel):
    require_clean_git: bool = True
    create_backup: bool = True
    allow_dependency_install: bool = False
    restart_services: bool = False
    run_health_checks: bool = True
    rollback_on_failure: bool = True
    services: list[ServiceRestartSpec] = []


class CompatibilitySpec(BaseModel):
    operating_systems: list[str] = []
    architectures: list[str] = []
    minimum_memory_mb: int | None = Field(default=None, ge=1)
    minimum_disk_mb: int | None = Field(default=None, ge=1)


class RemediationAction(BaseModel):
    type: Literal["command"]
    command: list[str] = Field(min_length=1)
    description: str = ""


class DependencySpec(BaseModel):
    name: str
    command: str
    classification: Literal[
        "required",
        "remediable",
        "manual",
    ] = "required"
    description: str = ""
    remediation: RemediationAction | None = None


class PreflightSpec(BaseModel):
    required_commands: list[str] = []
    dependencies: list[DependencySpec] = []


class TestsSpec(BaseModel):
    installer_engine: bool = False
    backend: bool = False
    node_agent: bool = False
    frontend: bool = False


class CommandHealthCheck(BaseModel):
    type: Literal["command"]
    name: str
    command: list[str] = Field(min_length=1)


class Manifest(BaseModel):
    feature_pack: FeaturePackInfo
    components: dict[str, ComponentSpec]
    operations: OperationsSpec = OperationsSpec()
    compatibility: CompatibilitySpec = CompatibilitySpec()
    preflight: PreflightSpec = PreflightSpec()
    tests: TestsSpec = TestsSpec()
    health_checks: list[CommandHealthCheck] = []
