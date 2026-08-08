from types import SimpleNamespace

from khan_agent import inventory


def test_memory_inventory_reads_proc_meminfo(monkeypatch):
    class FakePath:
        def read_text(self, errors="replace"):
            return "MemTotal:       32768000 kB\n"

    monkeypatch.setattr(inventory, "Path", lambda *_: FakePath())
    assert inventory._memory_total_bytes() == 32768000 * 1024


def test_docker_is_available_only_when_service_active(monkeypatch):
    monkeypatch.setattr(
        inventory.shutil,
        "which",
        lambda command: {
            "docker": "/usr/bin/docker",
            "systemctl": "/usr/bin/systemctl",
        }.get(command),
    )

    def fake_run(command, timeout=5.0):
        if command[0].endswith("systemctl"):
            return SimpleNamespace(returncode=0, stdout="active\n", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout="Docker version 29.6.0, build test\n",
            stderr="",
        )

    monkeypatch.setattr(inventory, "_run", fake_run)
    result = inventory._docker_inventory()

    assert result["installed"] is True
    assert result["active"] is True
    assert result["available"] is True
    assert "29.6.0" in result["version"]


def test_nvidia_tool_without_gpu_is_not_gpu_available(monkeypatch):
    monkeypatch.setattr(
        inventory.shutil,
        "which",
        lambda command: "/usr/bin/nvidia-smi" if command == "nvidia-smi" else None,
    )
    monkeypatch.setattr(
        inventory,
        "_run",
        lambda command, timeout=10.0: SimpleNamespace(
            returncode=9,
            stdout="",
            stderr="No devices were found",
        ),
    )

    result = inventory._nvidia_inventory()

    assert result["driver_tool_installed"] is True
    assert result["available"] is False
    assert result["gpus"] == []


def test_nvidia_gpu_is_available_only_after_successful_query(monkeypatch):
    monkeypatch.setattr(
        inventory.shutil,
        "which",
        lambda command: "/usr/bin/nvidia-smi" if command == "nvidia-smi" else None,
    )
    monkeypatch.setattr(
        inventory,
        "_run",
        lambda command, timeout=10.0: SimpleNamespace(
            returncode=0,
            stdout="0, NVIDIA RTX Test, GPU-123, 16384\n",
            stderr="",
        ),
    )

    result = inventory._nvidia_inventory()

    assert result["available"] is True
    assert result["gpus"][0]["name"] == "NVIDIA RTX Test"
    assert result["gpus"][0]["memory_total_mib"] == 16384
