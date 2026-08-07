from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

from kc_installer.models import Manifest


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


def memory_mb() -> int:
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


@dataclass(frozen=True)
class RemediationPolicyDecision:
    dependency_name: str
    action_type: str
    command: list[str]
    description: str
    eligible: bool
    reason: str


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
            )
        )

    return decisions
