from __future__ import annotations

import os
import platform
import re
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
    if platform.system() == "Windows":
        powershell = (
            shutil.which("powershell")
            or shutil.which("powershell.exe")
            or shutil.which("pwsh")
            or "powershell.exe"
        )
        if powershell:
            result = _run(
                [
                    powershell,
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)",
                ]
            )
            if result and result.returncode == 0:
                value = result.stdout.strip()
                if value:
                    return value

    try:
        for line in Path("/proc/cpuinfo").read_text(errors="replace").splitlines():
            if line.lower().startswith("model name") and ":" in line:
                return line.split(":", 1)[1].strip()
    except OSError:
        pass

    return platform.processor() or platform.machine()


def _memory_total_bytes() -> int:
    if platform.system() == "Windows":
        powershell = (
            shutil.which("powershell")
            or shutil.which("powershell.exe")
            or shutil.which("pwsh")
            or "powershell.exe"
        )
        if powershell:
            result = _run(
                [
                    powershell,
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
                ]
            )
            if result and result.returncode == 0:
                try:
                    return int(result.stdout.strip())
                except ValueError:
                    pass

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
    path = "/"

    if platform.system() == "Windows":
        system_drive = os.environ.get("SystemDrive", "C:")
        path = system_drive.rstrip("\\/") + "\\"

    try:
        root = shutil.disk_usage(path)
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
        "gpu_passthrough": _gpu_passthrough_inventory(),
    }




def _gpu_passthrough_inventory() -> dict[str, Any]:
    """Discover Linux PCI display GPUs suitable for explicit VM passthrough."""
    if platform.system() == "Windows":
        return {"available": False, "devices": [], "reason": "windows_host"}
    lspci = shutil.which("lspci")
    if not lspci:
        return {"available": False, "devices": [], "reason": "lspci_missing"}
    result = _run([lspci, "-Dnnk"], timeout=10.0)
    if result is None or result.returncode != 0:
        return {"available": False, "devices": [], "reason": "lspci_failed"}
    devices=[]; current=None
    for line in result.stdout.splitlines():
        if line and not line[0].isspace():
            if current: devices.append(current)
            m=re.match(r"^(?P<pci>[0-9a-fA-F:.]+)\s+.*?(VGA compatible controller|3D controller).*?\[(?P<vendor>[0-9a-fA-F]{4}):(?P<device>[0-9a-fA-F]{4})\]", line)
            current=None
            if m:
                pci=m.group("pci"); slot=pci.rsplit(".",1)[0]
                current={"pci_address":pci,"slot":slot.split(":",1)[1] if pci.count(":")>=2 else slot,"vendor_id":m.group("vendor").lower(),"device_id":m.group("device").lower(),"name":line.split("[",1)[0].split(None,1)[1].strip(),"driver":"","iommu_group":"","memory_total_mib":0}
        elif current:
            stripped=line.strip()
            if stripped.startswith("Kernel driver in use:"):
                current["driver"]=stripped.split(":",1)[1].strip()
    if current: devices.append(current)
    for item in devices:
        addr=item["pci_address"]
        group=Path("/sys/bus/pci/devices")/addr/"iommu_group"
        try: item["iommu_group"]=group.resolve().name if group.exists() else ""
        except OSError: item["iommu_group"]=""
        item["assignable"]=bool(item["iommu_group"] and item["driver"] in {"vfio-pci","vfio_pci"})
    return {"available": bool(devices), "assignable_count": sum(bool(d["assignable"]) for d in devices), "devices": devices}

def _virtualization_inventory() -> dict[str, Any]:
    if platform.system() == "Windows":
        return {
            "kvm_available": False,
            "libvirt_available": False,
            "virsh_installed": False,
            "qemu_installed": False,
            "libvirt_active": False,
        }

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


# KG-001 gaming inventory
_original_collect_safe_inventory = collect_safe_inventory

def collect_safe_inventory(*args, **kwargs):
    inventory = _original_collect_safe_inventory(*args, **kwargs)
    try:
        from khan_agent.gaming_inventory import collect_gaming_inventory
        inventory["gaming"] = collect_gaming_inventory()
    except Exception as exc:
        inventory["gaming"] = {"launchers": {}, "games": [], "streaming": {}, "discovery_error": type(exc).__name__}
    return inventory
