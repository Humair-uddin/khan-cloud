from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from khan_agent.virtualization import JobExecutionResult


class ProxmoxGamingVmError(RuntimeError):
    pass


def _run(command: list[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, shell=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProxmoxGamingVmError(str(exc)) from exc
    if result.returncode != 0:
        raise ProxmoxGamingVmError((result.stderr or result.stdout or "command failed").strip()[:1000])
    return result


def _require_backend() -> tuple[str, str]:
    qm, pvesh = shutil.which("qm"), shutil.which("pvesh")
    if not qm or not pvesh:
        raise ProxmoxGamingVmError("Proxmox qm/pvesh tooling is required.")
    return qm, pvesh


def _vmid(pvesh: str) -> int:
    raw = _run([pvesh, "get", "/cluster/nextid", "--output-format", "json"]).stdout.strip()
    try:
        value = int(json.loads(raw))
    except Exception:
        value = int(raw.strip('"'))
    if value < 100:
        raise ProxmoxGamingVmError("Invalid Proxmox next VMID.")
    return value


def _safe_slot(value: str) -> str:
    slot = value.strip()
    if not re.fullmatch(r"(?:[0-9a-fA-F]{4}:)?[0-9a-fA-F]{2}:[0-9a-fA-F]{2}", slot):
        raise ProxmoxGamingVmError("Invalid PCI slot for GPU passthrough.")
    return slot


def _safe_name(value: str, session_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-.")[:48]
    return cleaned or f"KC-GAME-{session_id[:8]}"


def _state_path(root: Path, session_id: str) -> Path:
    clean = re.sub(r"[^A-Za-z0-9-]", "", session_id)
    if not clean:
        raise ProxmoxGamingVmError("Invalid gaming session identifier.")
    return root / "gaming-vms" / f"{clean}.json"


def _write_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, sort_keys=True, indent=2), encoding="utf-8")
    temp.replace(path)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProxmoxGamingVmError("Gaming VM runtime state is corrupt.") from exc
    return value if isinstance(value, dict) else {}


def _vm_exists(qm: str, vmid: int) -> bool:
    return subprocess.run([qm, "config", str(vmid)], check=False, capture_output=True, text=True).returncode == 0


def _validate_template(qm: str, template_vmid: int) -> None:
    if template_vmid < 100 or not _vm_exists(qm, template_vmid):
        raise ProxmoxGamingVmError("Configured Windows gaming template does not exist.")
    config = _run([qm, "config", str(template_vmid)]).stdout
    if not re.search(r"(?m)^template:\s*1\s*$", config):
        raise ProxmoxGamingVmError("Configured Windows gaming source VM is not a Proxmox template.")
    if not re.search(r"(?m)^agent:\s*enabled=1", config):
        raise ProxmoxGamingVmError("Windows gaming template must have QEMU guest agent enabled.")


def _validate_storage_and_bridge(pvesh: str, storage: str, bridge: str) -> None:
    storages = _run([pvesh, "get", "/storage", "--output-format", "json"]).stdout
    networks = _run([pvesh, "get", "/nodes/localhost/network", "--output-format", "json"]).stdout
    try:
        storage_rows, network_rows = json.loads(storages), json.loads(networks)
    except json.JSONDecodeError as exc:
        raise ProxmoxGamingVmError("Unable to validate Proxmox storage/network inventory.") from exc
    if storage not in {str(x.get("storage")) for x in storage_rows if isinstance(x, dict)}:
        raise ProxmoxGamingVmError(f"Proxmox storage is unavailable: {storage}")
    if bridge not in {str(x.get("iface")) for x in network_rows if isinstance(x, dict)}:
        raise ProxmoxGamingVmError(f"Proxmox bridge is unavailable: {bridge}")


def _wait_qga(qm: str, vmid: int, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        ping = subprocess.run([qm, "agent", str(vmid), "ping"], check=False, capture_output=True, text=True)
        if ping.returncode == 0:
            return
        time.sleep(5)
    raise ProxmoxGamingVmError("Windows template QEMU guest agent did not become ready.")


def _bootstrap_guest(qm: str, vmid: int, *, control_plane_url: str, enrollment_code: str, timeout_seconds: int = 300) -> None:
    if not enrollment_code or not control_plane_url:
        raise ProxmoxGamingVmError("Guest enrollment handoff is incomplete.")
    _wait_qga(qm, vmid, timeout_seconds)
    # Values are passed as process arguments and never persisted in the hypervisor state file.
    script = r'''$ErrorActionPreference='Stop'
$cfg='C:\ProgramData\KhanCloud\Agent\config.yaml'
$py='C:\ProgramData\KhanCloud\Agent\runtime\.venv\Scripts\python.exe'
if (-not (Test-Path $cfg)) { throw 'KhanCloud Agent config missing from Windows template' }
if (-not (Test-Path $py)) { throw 'KhanCloud Agent runtime missing from Windows template' }
$raw=Get-Content -Raw -Path $cfg
if ($raw -notmatch '(?m)^\s*deployment_enrollment_code:') { throw 'deployment_enrollment_code key missing from template config' }
if ($raw -notmatch '(?m)^\s*control_plane_url:') { throw 'control_plane_url key missing from template config' }
$code=$args[0]; $url=$args[1]
$raw=[regex]::Replace($raw,'(?m)^(\s*deployment_enrollment_code:)\s*.*$','$1 "'+$code+'"')
$raw=[regex]::Replace($raw,'(?m)^(\s*control_plane_url:)\s*.*$','$1 "'+$url+'"')
Set-Content -Path $cfg -Value $raw -Encoding UTF8
& $py -m khan_agent --config $cfg --enroll
if ($LASTEXITCODE -ne 0) { throw 'KhanCloud Agent enrollment failed' }
$raw=Get-Content -Raw -Path $cfg
$raw=[regex]::Replace($raw,'(?m)^(\s*deployment_enrollment_code:)\s*.*$','$1 ""')
Set-Content -Path $cfg -Value $raw -Encoding UTF8
Restart-Service KhanCloudAgent
'''
    _run([qm, "guest", "exec", str(vmid), "--", "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script, enrollment_code, control_plane_url], timeout=float(timeout_seconds + 60))


def _configure_clone(qm: str, vmid: int, payload: dict[str, Any], slot: str) -> None:
    memory_mib = max(4096, int(payload.get("memory_bytes") or 0) // 1024**2)
    cpu = max(2, int(payload.get("cpu") or 0))
    bridge = str(payload.get("bridge") or "vmbr0")
    args = [qm, "set", str(vmid), "--cores", str(cpu), "--memory", str(memory_mib), "--machine", str(payload.get("machine") or "q35"), "--bios", str(payload.get("bios") or "ovmf"), "--agent", "enabled=1", "--hostpci0", f"{slot},pcie=1,x-vga=1", "--tags", "khan-gaming-managed"]
    _run(args)
    # A template may already have net0. Explicitly move it to the blueprint bridge when present.
    config = _run([qm, "config", str(vmid)]).stdout
    match = re.search(r"(?m)^net0:\s*([^\n]+)$", config)
    if match:
        net = re.sub(r"bridge=[^,]+", f"bridge={bridge}", match.group(1)) if "bridge=" in match.group(1) else match.group(1) + f",bridge={bridge}"
        _run([qm, "set", str(vmid), "--net0", net])


def _rollback_clone(qm: str, vmid: int, state_file: Path) -> None:
    subprocess.run([qm, "stop", str(vmid)], check=False, capture_output=True, text=True)
    subprocess.run([qm, "destroy", str(vmid), "--purge", "1"], check=False, capture_output=True, text=True)
    state_file.unlink(missing_ok=True)


def execute_proxmox_gaming_vm_job(job: dict[str, Any], *, execution_enabled: bool, state_root: Path) -> JobExecutionResult:
    job_type = str(job.get("job_type") or "")
    if not job_type.startswith("gaming.vm."):
        return JobExecutionResult("failed", {}, "Unsupported gaming VM job type.")
    if not execution_enabled:
        return JobExecutionResult("blocked", {}, "Virtualization execution is disabled by node policy.")
    try:
        qm, pvesh = _require_backend()
        payload = job.get("payload") or {}
        sid = str(payload.get("session_id") or "")
        state_file = _state_path(state_root, sid)
        state = _load_state(state_file)

        if job_type == "gaming.vm.create":
            # Idempotent retry: never clone a second VM after a successful create/report interruption.
            existing_vmid = int(state.get("vmid") or 0)
            if existing_vmid >= 100 and _vm_exists(qm, existing_vmid) and state.get("phase") == "ready_for_guest":
                return JobExecutionResult("succeeded", {"runtime_id": f"pve-{existing_vmid}", "vmid": existing_vmid, "gpu_pci_slot": state.get("gpu_pci_slot", ""), "guest_bootstrap_submitted": True, "idempotent_replay": True})

            template = int(payload.get("template_vmid") or 0)
            slot = _safe_slot(str(payload.get("gpu_pci_slot") or ""))
            storage, bridge = str(payload.get("storage") or "local-lvm"), str(payload.get("bridge") or "vmbr0")
            _validate_template(qm, template)
            _validate_storage_and_bridge(pvesh, storage, bridge)
            vmid = _vmid(pvesh)
            name = _safe_name(str(payload.get("name") or ""), sid)
            state = {"session_id": sid, "vmid": vmid, "runtime_id": f"pve-{vmid}", "gpu_pci_slot": slot, "phase": "allocated"}
            _write_state(state_file, state)
            try:
                _run([qm, "clone", str(template), str(vmid), "--name", name, "--full", "1", "--storage", storage], timeout=900)
                state["phase"] = "cloned"; _write_state(state_file, state)
                _configure_clone(qm, vmid, payload, slot)
                state["phase"] = "configured"; _write_state(state_file, state)
                _run([qm, "start", str(vmid)])
                state["phase"] = "booting"; _write_state(state_file, state)
                metadata = payload.get("blueprint_metadata") if isinstance(payload.get("blueprint_metadata"), dict) else {}
                qga_timeout = max(60, min(900, int(metadata.get("qga_timeout_seconds") or 300)))
                _bootstrap_guest(qm, vmid, control_plane_url=str(payload.get("control_plane_url") or ""), enrollment_code=str(payload.get("deployment_enrollment_code") or ""), timeout_seconds=qga_timeout)
                state["phase"] = "ready_for_guest"; state["status"] = "running"; _write_state(state_file, state)
                return JobExecutionResult("succeeded", {"runtime_id": state["runtime_id"], "vmid": vmid, "gpu_pci_slot": slot, "guest_bootstrap_submitted": True})
            except Exception:
                _rollback_clone(qm, vmid, state_file)
                raise

        vmid = int(state.get("vmid") or payload.get("vmid") or 0)
        if vmid < 100 or not _vm_exists(qm, vmid):
            raise ProxmoxGamingVmError("Gaming VM runtime state is missing a live VMID.")
        if job_type == "gaming.vm.start":
            _run([qm, "start", str(vmid)]); state["status"] = "running"; state["phase"] = "ready_for_guest"; _write_state(state_file, state)
            return JobExecutionResult("succeeded", {"runtime_id": f"pve-{vmid}", "vmid": vmid})
        if job_type == "gaming.vm.stop":
            shutdown = subprocess.run([qm, "shutdown", str(vmid), "--timeout", "45"], check=False, capture_output=True, text=True)
            if shutdown.returncode != 0:
                _run([qm, "stop", str(vmid)])
            state["status"] = "stopped"; state["phase"] = "stopped"; _write_state(state_file, state)
            return JobExecutionResult("succeeded", {"runtime_id": f"pve-{vmid}", "vmid": vmid})
        if job_type == "gaming.vm.delete":
            subprocess.run([qm, "stop", str(vmid)], check=False, capture_output=True, text=True)
            _run([qm, "destroy", str(vmid), "--purge", "1"], timeout=300)
            state_file.unlink(missing_ok=True)
            return JobExecutionResult("succeeded", {"runtime_id": f"pve-{vmid}", "vmid": vmid, "deleted": True})
        return JobExecutionResult("failed", {}, "Unsupported gaming VM action.")
    except ProxmoxGamingVmError as exc:
        return JobExecutionResult("failed", {}, str(exc))
    except Exception as exc:
        return JobExecutionResult("failed", {}, f"Unexpected Proxmox gaming VM failure: {type(exc).__name__}")
