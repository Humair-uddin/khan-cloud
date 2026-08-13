from __future__ import annotations

import shutil
import subprocess
from typing import Any


def _run(
    command: list[str],
    *,
    timeout: float = 5.0,
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def probe_proxmox_backend() -> dict[str, Any]:
    """
    Read-only discovery of the Proxmox gaming execution backend.

    This function must not create, modify, start, stop, or delete VMs.
    """

    qm = shutil.which("qm")
    pvesh = shutil.which("pvesh")

    result: dict[str, Any] = {
        "backend": "proxmox_vm",
        "available": False,
        "qm_installed": bool(qm),
        "pvesh_installed": bool(pvesh),
        "version": "",
    }

    if not qm:
        return result

    version = _run([qm, "--version"])
    if version and version.returncode == 0:
        result["version"] = version.stdout.strip()[:200]

    # Presence of qm is the minimum requirement for this backend.
    # VM-specific readiness will be evaluated separately from a job/profile
    # supplied VM identifier rather than hard-coding a VMID here.
    result["available"] = True

    return result


def probe_gaming_backend(execution_backend: str) -> dict[str, Any]:
    """
    Probe the execution backend selected by the deployment profile.
    """

    backend = execution_backend.strip().lower()

    if backend == "proxmox_vm":
        return probe_proxmox_backend()

    if backend == "wolf":
        return {
            "backend": "wolf",
            "available": bool(shutil.which("wolf")),
            "wolf_installed": bool(shutil.which("wolf")),
        }

    return {
        "backend": backend or "unknown",
        "available": False,
        "error": "unsupported_execution_backend",
    }


def probe_proxmox_vm(vm_id: int) -> dict[str, Any]:
    """
    Read-only inspection of one Proxmox VM.

    No lifecycle or configuration changes are permitted here.
    """

    qm = shutil.which("qm")

    result: dict[str, Any] = {
        "vm_id": vm_id,
        "exists": False,
        "state": "unknown",
        "running": False,
        "name": "",
        "vga": "",
        "hostpci": {},
        "gpu_passthrough_configured": False,
    }

    if not qm:
        result["error"] = "qm_not_available"
        return result

    status = _run([qm, "status", str(vm_id)])

    if status is None:
        result["error"] = "qm_status_failed"
        return result

    if status.returncode != 0:
        result["error"] = "vm_not_found"
        return result

    result["exists"] = True

    status_text = status.stdout.strip()
    if status_text.startswith("status:"):
        state = status_text.split(":", 1)[1].strip()
        result["state"] = state
        result["running"] = state == "running"

    config = _run([qm, "config", str(vm_id)])

    if config is None or config.returncode != 0:
        result["error"] = "vm_config_unavailable"
        return result

    for raw_line in config.stdout.splitlines():
        if ":" not in raw_line:
            continue

        key, value = raw_line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if key == "name":
            result["name"] = value
        elif key == "vga":
            result["vga"] = value
        elif key.startswith("hostpci"):
            result["hostpci"][key] = value

    result["gpu_passthrough_configured"] = bool(result["hostpci"])

    return result
