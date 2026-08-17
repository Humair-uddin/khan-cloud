from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
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



def locate_sunshine() -> Path | None:
    """Locate an existing Sunshine installation without modifying the host."""
    override = os.environ.get("KHAN_SUNSHINE_EXECUTABLE", "").strip()
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate

    discovered = shutil.which("sunshine")
    if discovered:
        return Path(discovered)

    if platform.system() == "Windows":
        roots = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        ]
        for root in roots:
            candidate = Path(root) / "Sunshine" / "sunshine.exe"
            if candidate.is_file():
                return candidate
    return None


def probe_nvidia_gpu(gpu_uuid: str) -> dict[str, Any]:
    """Read-only validation of the assigned NVIDIA GPU and installed driver stack."""
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "gpu_uuid": gpu_uuid, "error": "nvidia_smi_not_available"}
    result = _run(
        [
            executable,
            "--query-gpu=uuid,name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        timeout=10.0,
    )
    if result is None or result.returncode != 0:
        return {"available": False, "gpu_uuid": gpu_uuid, "error": "nvidia_query_failed"}
    for raw in result.stdout.splitlines():
        parts = [item.strip() for item in raw.split(",")]
        if len(parts) < 4 or parts[0] != gpu_uuid:
            continue
        try:
            memory_total_mib = int(parts[2])
        except ValueError:
            memory_total_mib = 0
        return {
            "available": True,
            "uuid": parts[0],
            "name": parts[1],
            "memory_total_mib": memory_total_mib,
            "driver_version": parts[3],
        }
    return {"available": False, "gpu_uuid": gpu_uuid, "error": "assigned_gpu_not_found"}

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

    if backend == "windows_native":
        sunshine = locate_sunshine()
        nvidia_smi = shutil.which("nvidia-smi")

        return {
            "backend": "windows_native",
            "available": bool(sunshine),
            "sunshine_installed": bool(sunshine),
            "nvidia_smi_installed": bool(nvidia_smi),
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


def locate_steam() -> Path | None:
    """Locate an existing Steam client without installing or modifying it."""
    override = os.environ.get("KHAN_STEAM_EXECUTABLE", "").strip()

    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate

    discovered = shutil.which("steam")

    if discovered:
        return Path(discovered)

    if platform.system() == "Windows":
        roots = [
            os.environ.get(
                "ProgramFiles(x86)",
                r"C:\Program Files (x86)",
            ),
            os.environ.get(
                "ProgramFiles",
                r"C:\Program Files",
            ),
        ]

        for root in roots:
            candidate = (
                Path(root)
                / "Steam"
                / "steam.exe"
            )

            if candidate.is_file():
                return candidate

    return None


def launch_steam_app(
    steam_executable: Path,
    app_id: str,
) -> dict[str, Any]:
    """
    Ask the existing Steam client to launch one installed AppID.

    Khan Cloud does not install, update, crack, modify, or bypass licensing
    for Steam or the requested title.
    """

    normalized = str(app_id).strip()

    if not normalized.isdigit() or int(normalized) <= 0:
        raise ValueError(
            "Steam AppID must be a positive integer."
        )

    command = [
        str(steam_executable),
        "-applaunch",
        normalized,
    ]

    if platform.system() == "Windows":
        from khan_agent.windows_interactive import (
            InteractiveSessionError,
            launch_in_active_session,
        )

        try:
            launched = launch_in_active_session(command)
        except InteractiveSessionError as exc:
            raise RuntimeError(
                f"Unable to start Steam AppID {normalized} "
                "in the active Windows user session."
            ) from exc

        return {
            "launcher_type": "steam",
            "launcher_game_id": normalized,
            "command_mode": "steam_applaunch",
            "launcher_pid": launched.pid,
            "session_id": launched.session_id,
            "execution_context": launched.execution_context,
        }

    try:
        process = subprocess.Popen(
            command,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        raise RuntimeError(
            f"Unable to start Steam AppID {normalized}."
        ) from exc

    return {
        "launcher_type": "steam",
        "launcher_game_id": normalized,
        "command_mode": "steam_applaunch",
        "launcher_pid": process.pid,
        "execution_context": "local_process",
    }
