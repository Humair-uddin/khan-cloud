from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from khan_agent.virtualization import JobExecutionResult

class ProxmoxGamingVmError(RuntimeError): pass

def _run(command:list[str], *, timeout:float=120.0):
    try: result=subprocess.run(command,check=False,capture_output=True,text=True,shell=False,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc: raise ProxmoxGamingVmError(str(exc)) from exc
    if result.returncode != 0: raise ProxmoxGamingVmError((result.stderr or result.stdout or "command failed").strip()[:500])
    return result

def _require_backend():
    qm=shutil.which("qm"); pvesh=shutil.which("pvesh")
    if not qm or not pvesh: raise ProxmoxGamingVmError("Proxmox qm/pvesh tooling is required.")
    return qm,pvesh

def _vmid(pvesh:str)->int:
    raw=_run([pvesh,"get","/cluster/nextid","--output-format","json"]).stdout.strip()
    try: value=int(json.loads(raw))
    except Exception: value=int(raw.strip('"'))
    if value < 100: raise ProxmoxGamingVmError("Invalid Proxmox next VMID.")
    return value

def _safe_slot(value:str)->str:
    slot=value.strip()
    if not re.fullmatch(r"(?:[0-9a-fA-F]{4}:)?[0-9a-fA-F]{2}:[0-9a-fA-F]{2}",slot):
        raise ProxmoxGamingVmError("Invalid PCI slot for GPU passthrough.")
    return slot

def _state_path(root:Path, session_id:str)->Path:
    clean=re.sub(r"[^A-Za-z0-9-]","",session_id)
    if not clean: raise ProxmoxGamingVmError("Invalid gaming session identifier.")
    return root/"gaming-vms"/f"{clean}.json"

def _write_state(path:Path,data:dict):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,sort_keys=True,indent=2),encoding="utf-8")

def _bootstrap_guest(qm:str, vmid:int, *, control_plane_url:str, enrollment_code:str):
    if not enrollment_code or not control_plane_url: raise ProxmoxGamingVmError("Guest enrollment handoff is incomplete.")
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        ping=subprocess.run([qm,"agent",str(vmid),"ping"],check=False,capture_output=True,text=True)
        if ping.returncode==0: break
        time.sleep(5)
    else: raise ProxmoxGamingVmError("Windows template QEMU guest agent did not become ready.")
    config=r"C:\ProgramData\KhanCloud\Agent\config.yaml"
    script = (
        "$p='" + config + "'; $c=Get-Content -Raw $p; "
        + r"$c=$c -replace '(?m)^\s*deployment_enrollment_code:.*$', '  deployment_enrollment_code: "
        + enrollment_code + "'; "
        + r"$c=$c -replace '(?m)^\s*control_plane_url:.*$', '  control_plane_url: "
        + control_plane_url + "'; "
        + "Set-Content -Path $p -Value $c -Encoding UTF8; "
        + r"& 'C:\ProgramData\KhanCloud\Agent\runtime\.venv\Scripts\python.exe' -m khan_agent --config $p --enroll; "
        + "Restart-Service KhanCloudAgent"
    )
    _run([qm,"guest","exec",str(vmid),"--","powershell.exe","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-Command",script],timeout=180)

def execute_proxmox_gaming_vm_job(job:dict[str,Any], *, execution_enabled:bool, state_root:Path)->JobExecutionResult:
    job_type=str(job.get("job_type") or "")
    if not job_type.startswith("gaming.vm."): return JobExecutionResult("failed",{},"Unsupported gaming VM job type.")
    if not execution_enabled: return JobExecutionResult("blocked",{},"Virtualization execution is disabled by node policy.")
    try:
        qm,pvesh=_require_backend(); p=job.get("payload") or {}; sid=str(p.get("session_id") or ""); state_file=_state_path(state_root,sid)
        state=json.loads(state_file.read_text()) if state_file.exists() else {}
        if job_type=="gaming.vm.create":
            template=int(p.get("template_vmid") or 0); slot=_safe_slot(str(p.get("gpu_pci_slot") or "")); vmid=_vmid(pvesh); name=f"KC-GAME-{sid[:8]}"
            try:
                _run([qm,"clone",str(template),str(vmid),"--name",name,"--full","1","--storage",str(p.get("storage") or "local-lvm")],timeout=600)
                mem=max(4096,int(p.get("memory_bytes") or 0)//1024**2); cpu=max(2,int(p.get("cpu") or 0))
                _run([qm,"set",str(vmid),"--cores",str(cpu),"--memory",str(mem),"--machine",str(p.get("machine") or "q35"),"--bios",str(p.get("bios") or "ovmf"),"--agent","enabled=1","--hostpci0",f"{slot},pcie=1,x-vga=1","--tags","khan-gaming-managed"])
                _run([qm,"start",str(vmid)])
                _bootstrap_guest(qm,vmid,control_plane_url=str(p.get("control_plane_url") or ""),enrollment_code=str(p.get("deployment_enrollment_code") or ""))
                state={"session_id":sid,"vmid":vmid,"runtime_id":f"pve-{vmid}","gpu_pci_slot":slot,"status":"running"}; _write_state(state_file,state)
                return JobExecutionResult("succeeded",{"runtime_id":state["runtime_id"],"vmid":vmid,"gpu_pci_slot":slot,"guest_bootstrap_submitted":True})
            except Exception:
                subprocess.run([qm,"stop",str(vmid)],check=False,capture_output=True); subprocess.run([qm,"destroy",str(vmid),"--purge","1"],check=False,capture_output=True); raise
        vmid=int(state.get("vmid") or p.get("vmid") or 0)
        if vmid < 100: raise ProxmoxGamingVmError("Gaming VM runtime state is missing VMID.")
        if job_type=="gaming.vm.start": _run([qm,"start",str(vmid)]); state["status"]="running"; _write_state(state_file,state); return JobExecutionResult("succeeded",{"runtime_id":f"pve-{vmid}","vmid":vmid})
        if job_type=="gaming.vm.stop":
            subprocess.run([qm,"shutdown",str(vmid),"--timeout","45"],check=False,capture_output=True,text=True); state["status"]="stopped"; _write_state(state_file,state); return JobExecutionResult("succeeded",{"runtime_id":f"pve-{vmid}","vmid":vmid})
        if job_type=="gaming.vm.delete":
            subprocess.run([qm,"stop",str(vmid)],check=False,capture_output=True); _run([qm,"destroy",str(vmid),"--purge","1"],timeout=300); state_file.unlink(missing_ok=True); return JobExecutionResult("succeeded",{"runtime_id":f"pve-{vmid}","vmid":vmid,"deleted":True})
        return JobExecutionResult("failed",{},"Unsupported gaming VM action.")
    except ProxmoxGamingVmError as exc:
        return JobExecutionResult("failed", {}, str(exc))
    except Exception as exc:
        return JobExecutionResult(
            "failed",
            {},
            f"Unexpected Proxmox gaming VM failure: {type(exc).__name__}",
        )
