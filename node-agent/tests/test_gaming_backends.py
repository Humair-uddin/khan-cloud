from __future__ import annotations

import subprocess

from khan_agent import gaming_backends


def test_proxmox_probe_is_unavailable_without_qm(monkeypatch):
    monkeypatch.setattr(
        gaming_backends.shutil,
        "which",
        lambda command: None,
    )

    result = gaming_backends.probe_proxmox_backend()

    assert result["backend"] == "proxmox_vm"
    assert result["available"] is False
    assert result["qm_installed"] is False


def test_proxmox_probe_detects_qm_without_modifying_vms(monkeypatch):
    def fake_which(command):
        mapping = {
            "qm": "/usr/sbin/qm",
            "pvesh": "/usr/bin/pvesh",
        }
        return mapping.get(command)

    commands = []

    def fake_run(command, *, timeout=5.0):
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="qm 7.0.2\n",
            stderr="",
        )

    monkeypatch.setattr(gaming_backends.shutil, "which", fake_which)
    monkeypatch.setattr(gaming_backends, "_run", fake_run)

    result = gaming_backends.probe_proxmox_backend()

    assert result["backend"] == "proxmox_vm"
    assert result["available"] is True
    assert result["qm_installed"] is True
    assert result["pvesh_installed"] is True
    assert result["version"] == "qm 7.0.2"

    assert commands == [["/usr/sbin/qm", "--version"]]


def test_wolf_backend_is_independent_from_proxmox(monkeypatch):
    monkeypatch.setattr(
        gaming_backends.shutil,
        "which",
        lambda command: "/usr/bin/wolf" if command == "wolf" else None,
    )

    result = gaming_backends.probe_gaming_backend("wolf")

    assert result == {
        "backend": "wolf",
        "available": True,
        "wolf_installed": True,
    }


def test_unknown_backend_fails_closed():
    result = gaming_backends.probe_gaming_backend("something_else")

    assert result["backend"] == "something_else"
    assert result["available"] is False
    assert result["error"] == "unsupported_execution_backend"


def test_proxmox_vm_probe_reads_status_and_gpu_passthrough(monkeypatch):
    monkeypatch.setattr(
        gaming_backends.shutil,
        "which",
        lambda command: "/usr/sbin/qm" if command == "qm" else None,
    )

    commands = []

    def fake_run(command, *, timeout=5.0):
        commands.append(command)

        if command[1] == "status":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="status: stopped\n",
                stderr="",
            )

        if command[1] == "config":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "name: Khan-Gaming-Windows-LAB\n"
                    "vga: none\n"
                    "hostpci0: 41:00,pcie=1,x-vga=1\n"
                ),
                stderr="",
            )

        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(gaming_backends, "_run", fake_run)

    result = gaming_backends.probe_proxmox_vm(200)

    assert result["vm_id"] == 200
    assert result["exists"] is True
    assert result["state"] == "stopped"
    assert result["running"] is False
    assert result["name"] == "Khan-Gaming-Windows-LAB"
    assert result["vga"] == "none"
    assert result["hostpci"]["hostpci0"] == "41:00,pcie=1,x-vga=1"
    assert result["gpu_passthrough_configured"] is True

    assert commands == [
        ["/usr/sbin/qm", "status", "200"],
        ["/usr/sbin/qm", "config", "200"],
    ]


def test_proxmox_vm_probe_reports_missing_vm(monkeypatch):
    monkeypatch.setattr(
        gaming_backends.shutil,
        "which",
        lambda command: "/usr/sbin/qm" if command == "qm" else None,
    )

    monkeypatch.setattr(
        gaming_backends,
        "_run",
        lambda command, timeout=5.0: subprocess.CompletedProcess(
            command,
            2,
            stdout="",
            stderr="Configuration file does not exist\n",
        ),
    )

    result = gaming_backends.probe_proxmox_vm(999)

    assert result["exists"] is False
    assert result["error"] == "vm_not_found"


def test_windows_native_backend_detects_sunshine(monkeypatch):
    def fake_which(command):
        mapping = {
            "sunshine": r"C:\Program Files\Sunshine\sunshine.exe",
            "nvidia-smi": r"C:\Windows\System32\nvidia-smi.exe",
        }
        return mapping.get(command)

    monkeypatch.setattr(gaming_backends.shutil, "which", fake_which)

    result = gaming_backends.probe_gaming_backend("windows_native")

    assert result["backend"] == "windows_native"
    assert result["available"] is True
    assert result["sunshine_installed"] is True
    assert result["nvidia_smi_installed"] is True


def test_windows_native_backend_is_unavailable_without_sunshine(monkeypatch):
    monkeypatch.setattr(
        gaming_backends.shutil,
        "which",
        lambda command: (
            r"C:\Windows\System32\nvidia-smi.exe"
            if command == "nvidia-smi"
            else None
        ),
    )

    result = gaming_backends.probe_gaming_backend("windows_native")

    assert result["backend"] == "windows_native"
    assert result["available"] is False
    assert result["sunshine_installed"] is False
    assert result["nvidia_smi_installed"] is True


def test_probe_nvidia_gpu_matches_assigned_uuid(monkeypatch):
    monkeypatch.setattr(
        gaming_backends.shutil,
        "which",
        lambda command: "/usr/bin/nvidia-smi" if command == "nvidia-smi" else None,
    )
    monkeypatch.setattr(
        gaming_backends,
        "_run",
        lambda command, timeout=5.0: subprocess.CompletedProcess(
            command,
            0,
            "GPU-A, NVIDIA RTX A, 8192, 595.95\nGPU-B, NVIDIA RTX B, 16384, 595.95\n",
            "",
        ),
    )
    result = gaming_backends.probe_nvidia_gpu("GPU-B")
    assert result["available"] is True
    assert result["uuid"] == "GPU-B"
    assert result["memory_total_mib"] == 16384
    assert result["driver_version"] == "595.95"


def test_locate_sunshine_honors_existing_override(monkeypatch, tmp_path):
    executable = tmp_path / "sunshine.exe"
    executable.write_text("test")
    monkeypatch.setenv("KHAN_SUNSHINE_EXECUTABLE", str(executable))
    monkeypatch.setattr(gaming_backends.shutil, "which", lambda command: None)
    assert gaming_backends.locate_sunshine() == executable
