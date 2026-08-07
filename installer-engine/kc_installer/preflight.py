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
