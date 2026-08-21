from pathlib import Path
import subprocess
from khan_agent import proxmox_gaming_vm

def test_invalid_gpu_slot_fails_closed():
    try: proxmox_gaming_vm._safe_slot("; rm -rf /")
    except proxmox_gaming_vm.ProxmoxGamingVmError: pass
    else: raise AssertionError("unsafe PCI slot accepted")

def test_executor_requires_policy():
    result=proxmox_gaming_vm.execute_proxmox_gaming_vm_job({"job_type":"gaming.vm.create","payload":{}},execution_enabled=False,state_root=Path("/tmp/kc-test"))
    assert result.status=="blocked"

def test_create_contract_uses_clone_gpu_qga_and_rollback():
    src=Path(proxmox_gaming_vm.__file__).read_text()
    for token in ('"clone"','"--hostpci0"','"agent"','_bootstrap_guest','"destroy"','"--purge"'):
        assert token in src

def test_enrollment_secret_not_written_to_runtime_state():
    src=Path(proxmox_gaming_vm.__file__).read_text()
    state_section=src[src.index('state={"session_id"'):src.index('return JobExecutionResult("succeeded"',src.index('state={"session_id"'))]
    assert "deployment_enrollment_code" not in state_section
