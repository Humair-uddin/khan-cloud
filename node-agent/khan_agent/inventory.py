from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _run(command: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess[str] | None:
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


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def _memory_total_bytes() -> int:
    try:
        for line in Path("/proc/meminfo").read_text(errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                return int(parts[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def _docker_inventory() -> dict[str, Any]:
    executable = shutil.which("docker")
    if not executable:
        return {
            "available": False,
            "installed": False,
            "active": False,
        }

    active = False
    systemctl = shutil.which("systemctl")
    if systemctl:
        result = _run([systemctl, "is-active", "docker"])
        active = bool(result and result.returncode == 0 and result.stdout.strip() == "active")

    version = ""
    result = _run([executable, "--version"])
    if result and result.returncode == 0:
        version = result.stdout.strip()[:200]

    return {
        "available": active,
        "installed": True,
        "active": active,
        "version": version,
    }


def _nvidia_inventory() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {
            "available": False,
            "driver_tool_installed": False,
            "gpus": [],
        }

    result = _run(
        [
            executable,
            "--query-gpu=index,name,uuid,memory.total",
            "--format=csv,noheader,nounits",
        ],
        timeout=10.0,
    )

    if result is None or result.returncode != 0:
        return {
            "available": False,
            "driver_tool_installed": True,
            "gpus": [],
            "status": "nvidia_smi_unavailable_or_no_gpu",
        }

    gpus: list[dict[str, Any]] = []
    for raw_line in result.stdout.splitlines():
        parts = [item.strip() for item in raw_line.split(",")]
        if len(parts) < 4:
            continue
        try:
            memory_mib = int(parts[3])
        except ValueError:
            memory_mib = 0
        gpus.append(
            {
                "index": parts[0],
                "name": parts[1],
                "uuid": parts[2],
                "memory_total_mib": memory_mib,
            }
        )

    return {
        "available": bool(gpus),
        "driver_tool_installed": True,
        "gpus": gpus,
    }


def _filesystem_inventory() -> dict[str, Any]:
    try:
        root = shutil.disk_usage("/")
        return {
            "root_total_bytes": root.total,
            "root_used_bytes": root.used,
            "root_free_bytes": root.free,
        }
    except OSError:
        return {}


def collect_safe_inventory() -> dict[str, Any]:
    return {
        "cpu": {
            "model": _cpu_model(),
            "logical_count": os.cpu_count() or 0,
        },
        "memory": {
            "total_bytes": _memory_total_bytes(),
        },
        "docker": _docker_inventory(),
        "nvidia": _nvidia_inventory(),
        "filesystem": _filesystem_inventory(),
        "virtualization": _virtualization_inventory(),
    }


def _virtualization_inventory() -> dict[str, Any]:
    kvm_device = Path("/dev/kvm")
    kvm_available = kvm_device.exists() and os.access(kvm_device, os.R_OK | os.W_OK)
    virsh = shutil.which("virsh")
    qemu = shutil.which("qemu-system-x86_64") or shutil.which("qemu-kvm")
    libvirt_active = False
    systemctl = shutil.which("systemctl")
    if systemctl:
        for unit in ("libvirtd", "virtqemud"):
            result = _run([systemctl, "is-active", unit])
            if result and result.returncode == 0 and result.stdout.strip() == "active":
                libvirt_active = True
                break
    return {
        "kvm_available": bool(kvm_available),
        "libvirt_available": bool(virsh and libvirt_active),
        "virsh_installed": bool(virsh),
        "qemu_installed": bool(qemu),
        "libvirt_active": libvirt_active,
    }
