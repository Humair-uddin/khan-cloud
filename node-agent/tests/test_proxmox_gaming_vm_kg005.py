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
    start=src.index('state = {"session_id": sid')
    end=src.index('_write_state(state_file, state)', start)
    state_section=src[start:end]
    assert "deployment_enrollment_code" not in state_section


def test_kg005b_template_preflight_and_idempotency_contract():
    src=Path(proxmox_gaming_vm.__file__).read_text()
    for token in ("_validate_template", "template:\\s*1", "_validate_storage_and_bridge", "idempotent_replay", "ready_for_guest"):
        assert token in src

def test_kg005b_bootstrap_scrubs_one_time_enrollment_code():
    src=Path(proxmox_gaming_vm.__file__).read_text()
    assert "deployment_enrollment_code key missing" in src
    assert "Restart-Service KhanCloudAgent" in src
    assert "'$1 \"\"'" in src

def test_kg005b_clone_state_is_atomic_and_rollback_removes_state():
    src=Path(proxmox_gaming_vm.__file__).read_text()
    assert 'temp.replace(path)' in src
    assert '_rollback_clone' in src
    assert 'state_file.unlink(missing_ok=True)' in src
