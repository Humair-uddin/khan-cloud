from pathlib import Path
from types import SimpleNamespace
import pytest
from khan_agent.state import AgentState, StateMachine
from khan_agent import virtualization as virt

def test_connected_can_begin_next_heartbeat_cycle():
    s=StateMachine()
    s.transition(AgentState.CONFIGURED)
    s.transition(AgentState.CONNECTING)
    s.transition(AgentState.CONNECTED)
    s.transition(AgentState.CONNECTING)
    assert s.current == AgentState.CONNECTING

def test_runtime_id_is_namespaced():
    assert virt._safe_runtime_id("1234-abcd") == "kc-1234-abcd"

def test_execution_remains_blocked_when_policy_disabled(monkeypatch):
    monkeypatch.setattr(virt,"_virtualization_inventory",lambda:{"kvm_available":True,"libvirt_available":True})
    result=virt.execute_virtualization_job({"job_type":"vps.create","payload":{}},execution_enabled=False)
    assert result.status=="blocked"

def test_domain_action_uses_system_libvirt(monkeypatch):
    calls=[]
    monkeypatch.setattr(virt,"_run",lambda cmd,timeout=60.0: calls.append(cmd) or SimpleNamespace(stdout="",returncode=0))
    result=virt._domain_action("kc-test","start")
    assert result.status=="succeeded"
    assert calls[0][:3]==["virsh","-c","qemu:///system"]

def test_activation_script_uses_nat_and_never_edits_netplan():
    root=Path(__file__).resolve().parents[1]
    source=(root/"deploy"/"activate-r7425-hypervisor.sh").read_text()
    assert "<forward mode='nat'/>" in source
    assert "192.168.250.1" in source
    assert "/etc/netplan" not in source
    assert "mkfs" not in source
    assert "parted" not in source


def test_vm_directory_is_explicitly_libvirt_traversable():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "khan_agent" / "virtualization.py").read_text()

    # The agent systemd unit uses UMask=0077. mkdir(mode=0755) alone would
    # therefore produce an inaccessible 0700 VM directory for libvirt-qemu.
    assert "instance_dir.chmod(0o755)" in source
