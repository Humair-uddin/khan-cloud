from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from kc_installer.models import Manifest


@dataclass(frozen=True)
class NvidiaGPU:
    model: str
    driver_version: str
    memory_total_mb: int | None = None
    operational: bool = True
    capabilities: tuple[str, ...] = ()

def _version_tuple(version: str) -> tuple[int, ...] | None:
    parts = version.strip().split(".")

    if not parts or any(not part.isdigit() for part in parts):
        return None

    return tuple(int(part) for part in parts)


def _driver_meets_minimum(
    actual: str,
    minimum: str,
) -> bool:
    actual_version = _version_tuple(actual)
    minimum_version = _version_tuple(minimum)

    if actual_version is None or minimum_version is None:
        return False

    length = max(len(actual_version), len(minimum_version))

    actual_version += (0,) * (length - len(actual_version))
    minimum_version += (0,) * (length - len(minimum_version))

    return actual_version >= minimum_version


def _driver_matches_branch(
    actual: str,
    branches: list[str],
) -> bool:
    actual_parts = actual.strip().split(".")

    for branch in branches:
        branch_parts = branch.strip().split(".")

        if not branch_parts:
            continue

        if actual_parts[:len(branch_parts)] == branch_parts:
            return True

    return False


def detect_nvidia_gpus() -> list[NvidiaGPU]:
    """Discover NVIDIA GPUs without modifying the host.

    nvidia-smi is treated as the authoritative runtime probe. Successful
    discovery proves that the installed NVIDIA stack is sufficiently
    operational for qualification; Khan Cloud does not replace that driver
    during normal provider onboarding.
    """
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            timeout=15.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []

    if completed.returncode != 0:
        return []

    devices: list[NvidiaGPU] = []

    for line in completed.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        parts = [part.strip() for part in line.split(",")]

        if len(parts) != 3:
            continue

        model, driver_version, memory_text = parts

        if not model:
            continue

        try:
            memory_total_mb = int(float(memory_text))
        except (TypeError, ValueError):
            memory_total_mb = None

        # nvidia-smi successfully querying the device means the GPU and
        # installed driver are operational enough for this discovery stage.
        #
        # NVIDIA gaming GPUs supported by the current Khan streaming stack
        # expose hardware video encoding. This capability is represented
        # explicitly so future discovery adapters can probe additional
        # vendors/capabilities without changing policy semantics.
        capabilities = (
            "hardware_video_encode",
        )

        devices.append(
            NvidiaGPU(
                model=model,
                driver_version=driver_version,
                memory_total_mb=memory_total_mb,
                operational=True,
                capabilities=capabilities,
            )
        )

    return devices


@dataclass(frozen=True)
class PreflightResult:
    name: str
    passed: bool
    actual: str
    required: str


def detect_os() -> str:
    path = Path("/etc/os-release")

    if path.exists():
        values: dict[str, str] = {}

        for line in path.read_text().splitlines():
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')

        if values.get("ID"):
            return values["ID"].lower()

    return platform.system().lower()


def _windows_memory_mb() -> int:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)

    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(
        ctypes.byref(status)
    ):
        raise OSError("GlobalMemoryStatusEx failed")

    return int(status.ullTotalPhys / (1024 * 1024))


def memory_mb() -> int:
    if os.name == "nt":
        return _windows_memory_mb()

    page_size = os.sysconf("SC_PAGE_SIZE")
    pages = os.sysconf("SC_PHYS_PAGES")
    return int((page_size * pages) / (1024 * 1024))


def free_disk_mb(path: Path) -> int:
    usage = shutil.disk_usage(path)
    return int(usage.free / (1024 * 1024))


def run_preflight(
    manifest: Manifest,
    target_dir: Path,
) -> list[PreflightResult]:
    results: list[PreflightResult] = []

    compatibility = manifest.compatibility

    if compatibility.operating_systems:
        actual = detect_os()
        allowed = [
            item.lower()
            for item in compatibility.operating_systems
        ]

        results.append(
            PreflightResult(
                name="operating_system",
                passed=actual in allowed,
                actual=actual,
                required=", ".join(allowed),
            )
        )

    if compatibility.architectures:
        actual = platform.machine().lower()
        allowed = [
            item.lower()
            for item in compatibility.architectures
        ]

        results.append(
            PreflightResult(
                name="architecture",
                passed=actual in allowed,
                actual=actual,
                required=", ".join(allowed),
            )
        )

    if compatibility.minimum_memory_mb is not None:
        actual = memory_mb()

        results.append(
            PreflightResult(
                name="memory_mb",
                passed=actual >= compatibility.minimum_memory_mb,
                actual=str(actual),
                required=str(compatibility.minimum_memory_mb),
            )
        )

    if compatibility.minimum_disk_mb is not None:
        actual = free_disk_mb(target_dir)

        results.append(
            PreflightResult(
                name="free_disk_mb",
                passed=actual >= compatibility.minimum_disk_mb,
                actual=str(actual),
                required=str(compatibility.minimum_disk_mb),
            )
        )

    qualification = manifest.qualification

    needs_gpu_discovery = (
        qualification is not None
        and (
            qualification.gpu.required
            or qualification.driver.required
        )
    )

    nvidia_devices = (
        detect_nvidia_gpus()
        if needs_gpu_discovery
        else []
    )

    # --------------------------------------------------------
    # GPU qualification
    # --------------------------------------------------------

    if qualification is not None and qualification.gpu.required:
        gpu_policy = qualification.gpu

        if not nvidia_devices:
            if gpu_policy.qualification_mode == "capability":
                required_parts = []

                if gpu_policy.vendor:
                    required_parts.append(
                        f"vendor={gpu_policy.vendor}"
                    )

                if gpu_policy.minimum_vram_mb is not None:
                    required_parts.append(
                        f"VRAM>={gpu_policy.minimum_vram_mb}MB"
                    )

                if gpu_policy.require_operational_gpu:
                    required_parts.append("operational GPU")

                required_parts.extend(
                    f"capability={capability}"
                    for capability
                    in gpu_policy.required_capabilities
                )

                required = (
                    "; ".join(required_parts)
                    or "qualified GPU"
                )
            else:
                required = (
                    ", ".join(gpu_policy.approved_models)
                    or "approved GPU"
                )

            results.append(
                PreflightResult(
                    name="gpu_qualification",
                    passed=False,
                    actual="not detected",
                    required=required,
                )
            )

        elif gpu_policy.qualification_mode == "capability":
            required_vendor = (
                gpu_policy.vendor.strip().casefold()
                if gpu_policy.vendor
                else None
            )

            required_capabilities = {
                item.strip().casefold()
                for item in gpu_policy.required_capabilities
                if item.strip()
            }

            def qualifies(device: NvidiaGPU) -> bool:
                if (
                    required_vendor == "nvidia"
                    and "nvidia"
                    not in device.model.casefold()
                ):
                    return False

                if (
                    gpu_policy.minimum_vram_mb is not None
                    and (
                        device.memory_total_mb is None
                        or device.memory_total_mb
                        < gpu_policy.minimum_vram_mb
                    )
                ):
                    return False

                if (
                    gpu_policy.require_operational_gpu
                    and not device.operational
                ):
                    return False

                device_capabilities = {
                    item.strip().casefold()
                    for item in device.capabilities
                }

                if not required_capabilities.issubset(
                    device_capabilities
                ):
                    return False

                return True

            qualified_device = next(
                (
                    device
                    for device in nvidia_devices
                    if qualifies(device)
                ),
                None,
            )

            required_parts = []

            if gpu_policy.vendor:
                required_parts.append(
                    f"vendor={gpu_policy.vendor}"
                )

            if gpu_policy.minimum_vram_mb is not None:
                required_parts.append(
                    f"VRAM>={gpu_policy.minimum_vram_mb}MB"
                )

            if gpu_policy.require_operational_gpu:
                required_parts.append("operational GPU")

            required_parts.extend(
                f"capability={capability}"
                for capability
                in gpu_policy.required_capabilities
            )

            required = (
                "; ".join(required_parts)
                or "capability-qualified GPU"
            )

            if qualified_device is not None:
                actual_parts = [
                    qualified_device.model,
                ]

                if qualified_device.memory_total_mb is not None:
                    actual_parts.append(
                        f"{qualified_device.memory_total_mb}MB VRAM"
                    )

                actual_parts.extend(
                    qualified_device.capabilities
                )

                results.append(
                    PreflightResult(
                        name="gpu_qualification",
                        passed=True,
                        actual="; ".join(actual_parts),
                        required=required,
                    )
                )
            else:
                actual_devices = []

                for device in nvidia_devices:
                    details = [device.model]

                    if device.memory_total_mb is None:
                        details.append("VRAM=unknown")
                    else:
                        details.append(
                            f"VRAM={device.memory_total_mb}MB"
                        )

                    details.append(
                        "operational=yes"
                        if device.operational
                        else "operational=no"
                    )

                    if device.capabilities:
                        details.append(
                            "capabilities="
                            + ",".join(device.capabilities)
                        )
                    else:
                        details.append("capabilities=none")

                    actual_devices.append(
                        "[" + "; ".join(details) + "]"
                    )

                results.append(
                    PreflightResult(
                        name="gpu_qualification",
                        passed=False,
                        actual=", ".join(actual_devices),
                        required=required,
                    )
                )

        else:
            # Legacy allowlist mode remains supported for previously
            # generated/signed feature packs.
            approved_models = {
                model.strip().casefold()
                for model in gpu_policy.approved_models
            }

            approved_device = next(
                (
                    device
                    for device in nvidia_devices
                    if device.model.strip().casefold()
                    in approved_models
                ),
                None,
            )

            results.append(
                PreflightResult(
                    name="gpu_qualification",
                    passed=approved_device is not None,
                    actual=(
                        approved_device.model
                        if approved_device is not None
                        else ", ".join(
                            device.model
                            for device in nvidia_devices
                        )
                    ),
                    required=(
                        ", ".join(gpu_policy.approved_models)
                        or "approved GPU"
                    ),
                )
            )

    # --------------------------------------------------------
    # NVIDIA driver qualification
    # --------------------------------------------------------

    if (
        qualification is not None
        and qualification.driver.required
    ):
        driver_policy = qualification.driver

        driver_versions = [
            device.driver_version.strip()
            for device in nvidia_devices
            if device.driver_version.strip()
        ]

        if not driver_versions:
            results.append(
                PreflightResult(
                    name="driver_qualification",
                    passed=False,
                    actual="not detected",
                    required=(
                        driver_policy.minimum_version
                        or ", ".join(
                            driver_policy.approved_branches
                        )
                        or "installed NVIDIA driver"
                    ),
                )
            )
        else:
            actual = driver_versions[0]

            minimum_ok = (
                True
                if driver_policy.minimum_version is None
                else _driver_meets_minimum(
                    actual,
                    driver_policy.minimum_version,
                )
            )

            branch_ok = (
                True
                if not driver_policy.approved_branches
                else _driver_matches_branch(
                    actual,
                    driver_policy.approved_branches,
                )
            )

            passed = minimum_ok and branch_ok

            requirements = []

            if driver_policy.minimum_version is not None:
                requirements.append(
                    f">={driver_policy.minimum_version}"
                )

            if driver_policy.approved_branches:
                requirements.append(
                    "branch "
                    + "/".join(
                        driver_policy.approved_branches
                    )
                )

            results.append(
                PreflightResult(
                    name="driver_qualification",
                    passed=passed,
                    actual=actual,
                    required=(
                        "; ".join(requirements)
                        or "installed NVIDIA driver"
                    ),
                )
            )

    for command in manifest.preflight.required_commands:
        location = shutil.which(command)

        results.append(
            PreflightResult(
                name=f"command:{command}",
                passed=location is not None,
                actual=location or "missing",
                required="available",
            )
        )

    return results


@dataclass(frozen=True)
class DependencyResult:
    name: str
    classification: str
    available: bool
    command: str
    description: str


def classify_dependencies(
    manifest: Manifest,
) -> list[DependencyResult]:
    results: list[DependencyResult] = []

    for dependency in manifest.preflight.dependencies:
        available = shutil.which(dependency.command) is not None

        results.append(
            DependencyResult(
                name=dependency.name,
                classification=dependency.classification,
                available=available,
                command=dependency.command,
                description=dependency.description,
            )
        )

    return results


@dataclass(frozen=True)
class RemediationPlanItem:
    dependency_name: str
    action_type: str
    command: list[str]
    description: str


def build_remediation_plan(
    manifest: Manifest,
) -> list[RemediationPlanItem]:
    plan: list[RemediationPlanItem] = []

    dependency_results = {
        item.name: item
        for item in classify_dependencies(manifest)
    }

    for dependency in manifest.preflight.dependencies:
        result = dependency_results[dependency.name]

        if result.available:
            continue

        if dependency.classification != "remediable":
            continue

        if dependency.remediation is None:
            continue

        plan.append(
            RemediationPlanItem(
                dependency_name=dependency.name,
                action_type=dependency.remediation.type,
                command=list(dependency.remediation.command),
                description=dependency.remediation.description,
            )
        )

    return plan




_BLOCKED_REMEDIATION_EXECUTABLES = {
    "sh", "bash", "dash", "zsh", "fish", "csh", "tcsh",
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh",
}

def remediation_command_allowed(command: list[str]) -> tuple[bool, str]:
    if not command or not command[0].strip():
        return False, "remediation command is empty"
    if any("\x00" in item for item in command):
        return False, "remediation command contains NUL data"
    executable = Path(command[0]).name.lower()
    if executable in _BLOCKED_REMEDIATION_EXECUTABLES:
        return False, "shell interpreters are prohibited for remediation"
    return True, "allowed"


@dataclass(frozen=True)
class RemediationPolicyDecision:
    dependency_name: str
    action_type: str
    command: list[str]
    description: str
    eligible: bool
    reason: str
    mutation_policy: str = "missing_only"
    verify_after_execution: bool = True


def evaluate_remediation_policy(
    manifest: Manifest,
    *,
    dry_run: bool,
    trusted_package: bool = False,
) -> list[RemediationPolicyDecision]:
    """
    Evaluate whether manifest-approved remediation actions would be
    eligible for future execution.

    This function DOES NOT execute remediation.

    `trusted_package` must come from an external trust/signature
    verification mechanism. The manifest's self-declared `signed`
    field is intentionally not treated as proof of trust.
    """

    plan = build_remediation_plan(manifest)
    decisions: list[RemediationPolicyDecision] = []

    for action in plan:
        if dry_run:
            eligible = False
            reason = "dry-run prohibits remediation execution"
        elif not manifest.operations.allow_dependency_install:
            eligible = False
            reason = "dependency installation is not permitted"
        elif not trusted_package:
            eligible = False
            reason = "package trust has not been verified"
        else:
            command_allowed, command_reason = remediation_command_allowed(
                list(action.command)
            )
            if not command_allowed:
                eligible = False
                reason = command_reason
            else:
                eligible = True
                reason = "eligible"

        decisions.append(
            RemediationPolicyDecision(
                dependency_name=action.dependency_name,
                action_type=action.action_type,
                command=list(action.command),
                description=action.description,
                eligible=eligible,
                reason=reason,
                mutation_policy="missing_only",
                verify_after_execution=True,
            )
        )

    return decisions


def classify_gpu_experience_tier(
    memory_total_mb: int,
    quality_policy: dict,
) -> str | None:
    """Return the highest VRAM-backed experience tier satisfied.

    VRAM is only one qualification input. Calling this function does
    not itself qualify a GPU; operational/capability checks happen
    separately.
    """
    tiers = quality_policy.get("tiers", {})

    ranked = []

    for name, definition in tiers.items():
        minimum = definition.get("minimum_vram_mb")

        if isinstance(minimum, int):
            ranked.append((minimum, name))

    eligible = [
        (minimum, name)
        for minimum, name in ranked
        if memory_total_mb >= minimum
    ]

    if not eligible:
        return None

    return max(eligible, key=lambda item: item[0])[1]
