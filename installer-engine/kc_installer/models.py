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


class DeploymentSpec(BaseModel):
    purpose: str
    platform: Literal["linux", "windows"]
    execution_backend: str | None = None
    streaming_backend: str | None = None


class GPUQualificationSpec(BaseModel):
    required: bool = False

    # "capability" is the production gaming policy.
    # "allowlist" remains accepted for old signed feature packs.
    qualification_mode: Literal["capability", "allowlist"] = "capability"

    # Legacy compatibility only.
    approved_models: list[str] = []

    vendor: str | None = None
    minimum_vram_mb: int | None = None
    required_capabilities: list[str] = []
    require_operational_gpu: bool = False
    quality_policy: dict = {}


class DriverQualificationSpec(BaseModel):
    vendor: str | None = None
    required: bool = False

    # Customer-owned gaming PCs preserve a functioning driver.
    management: Literal[
        "preserve_existing",
        "managed",
    ] = "preserve_existing"

    require_operational: bool = False
    automatic_upgrade: bool = False

    # Legacy compatibility for existing feature packs.
    minimum_version: str | None = None
    approved_branches: list[str] = []


class WorkloadQualificationSpec(BaseModel):
    primary: list[str] = []
    optional_interruptible: list[str] = []


class QualificationSpec(BaseModel):
    gpu: GPUQualificationSpec = GPUQualificationSpec()
    driver: DriverQualificationSpec = DriverQualificationSpec()
    workloads: WorkloadQualificationSpec = WorkloadQualificationSpec()


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

    # Remediation V2 safety contract.
    #
    # "missing_only" means Khan Cloud may execute this action only
    # when the declared dependency is absent at execution time.
    # This prevents an old remediation plan from modifying software
    # that became available after planning.
    mutation_policy: Literal["missing_only"] = "missing_only"

    # Automatic remediation must prove the dependency became usable
    # after mutation. This remains explicit in the manifest contract.
    verify_after_execution: bool = True


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


class ArtifactSourceSpec(BaseModel):
    type: Literal[
        "vendor_url",
        "khan_artifact",
        "local_cache",
        "host_projection",
    ]
    url: str | None = None


class ImageArtifactSpec(BaseModel):
    id: str
    version: str
    stage: Literal[
        "windows_source",
        "image_build",
        "post_deploy",
        "host_specific",
        "session",
    ]
    source: ArtifactSourceSpec
    sha256: str = ""
    architecture: str = "any"
    license: str = ""
    signer: str = ""
    total_bytes: int = Field(default=0, ge=0)
    install: dict = {}
    validation: dict = {}


class ImageRecipeSpec(BaseModel):
    id: str
    version: str
    windows: dict = {}
    artifacts: list[ImageArtifactSpec] = []


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
    deployment: DeploymentSpec | None = None
    qualification: QualificationSpec | None = None
    components: dict[str, ComponentSpec]
    operations: OperationsSpec = OperationsSpec()
    compatibility: CompatibilitySpec = CompatibilitySpec()
    preflight: PreflightSpec = PreflightSpec()
    tests: TestsSpec = TestsSpec()
    health_checks: list[CommandHealthCheck] = []
    image_recipe: ImageRecipeSpec | None = None
