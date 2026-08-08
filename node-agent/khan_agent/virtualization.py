from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from khan_agent.inventory import _virtualization_inventory


@dataclass(frozen=True)
class JobExecutionResult:
    status: str
    result: dict[str, Any]
    error_message: str = ""


class VirtualizationExecutionError(RuntimeError):
    pass


def _run(command: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command, check=False, capture_output=True, text=True,
            shell=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VirtualizationExecutionError(str(exc)) from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "command failed").strip()
        raise VirtualizationExecutionError(message[:500])
    return result


def _safe_runtime_id(vps_id: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9-]", "", vps_id)
    if not clean:
        raise VirtualizationExecutionError("Invalid VPS identifier.")
    return f"kc-{clean[:36]}"


def _paths(storage_root: Path, runtime_id: str) -> tuple[Path, Path, Path]:
    instances = storage_root / "instances" / runtime_id
    return instances, instances / "disk.qcow2", instances / "seed.iso"


def _write_cloud_init(directory: Path, runtime_id: str) -> tuple[Path, Path]:
    user_data = directory / "user-data"
    meta_data = directory / "meta-data"
    user_data.write_text(
        "#cloud-config\n"
        f"hostname: {runtime_id}\n"
        "manage_etc_hosts: true\n"
        "ssh_pwauth: false\n"
        "disable_root: true\n"
        "package_update: false\n"
        "runcmd:\n"
        "  - [ sh, -c, 'echo Khan Cloud VPS ready > /var/tmp/khan-cloud-ready' ]\n"
    )
    meta_data.write_text(
        f"instance-id: {runtime_id}\nlocal-hostname: {runtime_id}\n"
    )
    return user_data, meta_data


def _lease_ip(runtime_id: str, *, timeout_seconds: int = 75) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["virsh", "-c", "qemu:///system", "domifaddr", runtime_id, "--source", "lease"],
            check=False, capture_output=True, text=True, shell=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "ipv4" in line.lower() and "/" in line:
                    parts = line.split()
                    if parts:
                        address = parts[-1].split("/", 1)[0]
                        if address and address != "-":
                            return address
        time.sleep(3)
    return ""


def _create(job: dict[str, Any], *, storage_root: Path, base_image: Path, network_name: str) -> JobExecutionResult:
    payload = job.get("payload") or {}
    vps_id = str(payload.get("vps_id", ""))
    runtime_id = _safe_runtime_id(vps_id)
    vcpu = int(payload.get("vcpu", 0))
    memory_bytes = int(payload.get("memory_bytes", 0))
    disk_bytes = int(payload.get("disk_bytes", 0))
    if vcpu < 1 or memory_bytes < 512 * 1024**2 or disk_bytes < 8 * 1024**3:
        raise VirtualizationExecutionError("Invalid VPS resource request.")
    if not base_image.is_file():
        raise VirtualizationExecutionError(f"Base image missing: {base_image}")

    instance_dir, disk_path, seed_path = _paths(storage_root, runtime_id)
    if instance_dir.exists():
        raise VirtualizationExecutionError("VPS runtime directory already exists.")
    instance_dir.mkdir(parents=True, mode=0o755)
    # systemd runs the agent with UMask=0077. Explicit chmod is required
    # so libvirt-qemu can traverse the VM directory and read its disk/seed.
    instance_dir.chmod(0o755)
    try:
        _run([
            "qemu-img", "create", "-f", "qcow2", "-F", "qcow2",
            "-b", str(base_image), str(disk_path), str(disk_bytes),
        ])
        user_data, meta_data = _write_cloud_init(instance_dir, runtime_id)
        _run(["cloud-localds", str(seed_path), str(user_data), str(meta_data)])
        for item in (disk_path, seed_path):
            item.chmod(0o644)

        memory_mib = max(512, memory_bytes // 1024**2)
        _run([
            "virt-install",
            "--connect", "qemu:///system",
            "--name", runtime_id,
            "--memory", str(memory_mib),
            "--vcpus", str(vcpu),
            "--import",
            "--disk", f"path={disk_path},format=qcow2,bus=virtio",
            "--disk", f"path={seed_path},device=cdrom",
            "--network", f"network={network_name},model=virtio",
            "--os-variant", "ubuntu24.04",
            "--graphics", "none",
            "--noautoconsole",
            "--wait", "0",
        ], timeout=120)
        ip = _lease_ip(runtime_id)
        return JobExecutionResult(
            "succeeded",
            {"runtime_id": runtime_id, "primary_ip": ip, "network": network_name},
        )
    except Exception:
        subprocess.run(
            ["virsh", "-c", "qemu:///system", "destroy", runtime_id],
            check=False, capture_output=True,
        )
        subprocess.run(
            ["virsh", "-c", "qemu:///system", "undefine", runtime_id, "--nvram"],
            check=False, capture_output=True,
        )
        shutil.rmtree(instance_dir, ignore_errors=True)
        raise


def _domain_action(runtime_id: str, action: str) -> JobExecutionResult:
    if not runtime_id:
        raise VirtualizationExecutionError("VPS runtime_id is missing.")
    if action == "start":
        _run(["virsh", "-c", "qemu:///system", "start", runtime_id])
        return JobExecutionResult("succeeded", {"runtime_id": runtime_id})
    if action == "stop":
        _run(["virsh", "-c", "qemu:///system", "shutdown", runtime_id])
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            state = _run(["virsh", "-c", "qemu:///system", "domstate", runtime_id]).stdout.strip().lower()
            if "shut off" in state:
                return JobExecutionResult("succeeded", {"runtime_id": runtime_id})
            time.sleep(2)
        _run(["virsh", "-c", "qemu:///system", "destroy", runtime_id])
        return JobExecutionResult("succeeded", {"runtime_id": runtime_id, "forced": True})
    if action == "reboot":
        _run(["virsh", "-c", "qemu:///system", "reboot", runtime_id])
        return JobExecutionResult("succeeded", {"runtime_id": runtime_id})
    raise VirtualizationExecutionError("Unsupported VPS domain action.")


def _delete(runtime_id: str, storage_root: Path) -> JobExecutionResult:
    if not runtime_id:
        raise VirtualizationExecutionError("VPS runtime_id is missing.")
    subprocess.run(
        ["virsh", "-c", "qemu:///system", "destroy", runtime_id],
        check=False, capture_output=True, text=True,
    )
    _run(["virsh", "-c", "qemu:///system", "undefine", runtime_id, "--nvram"])
    shutil.rmtree(storage_root / "instances" / runtime_id, ignore_errors=True)
    return JobExecutionResult("succeeded", {"runtime_id": runtime_id, "deleted": True})


def execute_virtualization_job(
    job: dict[str, Any],
    *,
    execution_enabled: bool,
    storage_root: Path = Path("/var/lib/khan-cloud/vps"),
    base_image_path: Path = Path("/var/lib/khan-cloud/vps/images/ubuntu-24.04-base.qcow2"),
    network_name: str = "kc-vps-net",
) -> JobExecutionResult:
    job_type = str(job.get("job_type", ""))
    if not job_type.startswith("vps."):
        return JobExecutionResult("failed", {}, "Unsupported node job type.")

    capability = _virtualization_inventory()
    if not execution_enabled:
        return JobExecutionResult("blocked", {"virtualization": capability}, "VPS execution is disabled by node policy.")
    if not capability.get("kvm_available") or not capability.get("libvirt_available"):
        return JobExecutionResult("blocked", {"virtualization": capability}, "KVM/libvirt are not ready on this node.")

    try:
        if job_type == "vps.create":
            return _create(job, storage_root=storage_root, base_image=base_image_path, network_name=network_name)
        payload = job.get("payload") or {}
        runtime_id = str(payload.get("runtime_id", ""))
        if job_type == "vps.start":
            return _domain_action(runtime_id, "start")
        if job_type == "vps.stop":
            return _domain_action(runtime_id, "stop")
        if job_type == "vps.reboot":
            return _domain_action(runtime_id, "reboot")
        if job_type == "vps.delete":
            return _delete(runtime_id, storage_root)
        return JobExecutionResult("failed", {}, "Unsupported VPS job type.")
    except VirtualizationExecutionError as exc:
        return JobExecutionResult("failed", {"virtualization": capability}, str(exc))
