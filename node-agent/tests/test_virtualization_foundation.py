from types import SimpleNamespace

from khan_agent import inventory
from khan_agent.virtualization import execute_virtualization_job


def test_virtualization_inventory_requires_kvm_and_active_libvirt(monkeypatch):
    class FakePath:
        def exists(self): return True
    monkeypatch.setattr(inventory, "Path", lambda *_: FakePath())
    monkeypatch.setattr(inventory.os, "access", lambda *_: True)
    monkeypatch.setattr(
        inventory.shutil,
        "which",
        lambda name: {
            "virsh": "/usr/bin/virsh",
            "qemu-system-x86_64": "/usr/bin/qemu-system-x86_64",
            "systemctl": "/usr/bin/systemctl",
        }.get(name),
    )
    monkeypatch.setattr(
        inventory,
        "_run",
        lambda command, timeout=5.0: SimpleNamespace(returncode=0, stdout="active\n", stderr=""),
    )
    result = inventory._virtualization_inventory()
    assert result["kvm_available"] is True
    assert result["libvirt_available"] is True


def test_vps_job_blocked_when_execution_disabled(monkeypatch):
    monkeypatch.setattr(
        "khan_agent.virtualization._virtualization_inventory",
        lambda: {"kvm_available": True, "libvirt_available": True},
    )
    result = execute_virtualization_job({"job_type": "vps.create"}, execution_enabled=False)
    assert result.status == "blocked"
    assert "disabled" in result.error_message.lower()


def test_vps_job_blocked_when_hypervisor_not_ready(monkeypatch):
    monkeypatch.setattr(
        "khan_agent.virtualization._virtualization_inventory",
        lambda: {"kvm_available": False, "libvirt_available": False},
    )
    result = execute_virtualization_job({"job_type": "vps.create"}, execution_enabled=True)
    assert result.status == "blocked"
    assert "not ready" in result.error_message.lower()


def test_unknown_node_job_never_executes(monkeypatch):
    result = execute_virtualization_job({"job_type": "shell.command"}, execution_enabled=True)
    assert result.status == "failed"
