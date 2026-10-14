from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from khan_agent import windows_presentation


def test_y16_graphics_snapshot_records_only_allowlisted_basenames(
    monkeypatch,
):
    mappings = [
        SimpleNamespace(
            path=r"C:\Windows\System32\dxgi.dll"
        ),
        SimpleNamespace(
            path=r"C:\Windows\System32\d3d11.dll"
        ),
        SimpleNamespace(
            path=r"C:\Windows\System32\D3D11.DLL"
        ),
        SimpleNamespace(
            path=(
                r"C:\Program Files (x86)\Steam"
                r"\gameoverlayrenderer64.dll"
            )
        ),
        SimpleNamespace(
            path=r"C:\Secret\unrelated-private-module.dll"
        ),
        SimpleNamespace(path=""),
    ]

    fake_psutil = SimpleNamespace(
        Process=lambda pid: SimpleNamespace(
            memory_maps=lambda: mappings,
        )
    )

    monkeypatch.setitem(
        sys.modules,
        "psutil",
        fake_psutil,
    )

    result = (
        windows_presentation
        ._graphics_module_snapshot(22260)
    )

    assert result == {
        "pid": 22260,
        "ok": True,
        "modules": [
            "d3d11.dll",
            "dxgi.dll",
            "gameoverlayrenderer64.dll",
        ],
        "error_type": "",
    }

    serialized = repr(result)

    assert "C:\\Secret" not in serialized
    assert "unrelated-private-module.dll" not in serialized


def test_y16_graphics_snapshot_failure_is_diagnostic_only(
    monkeypatch,
):
    class BrokenProcess:
        def __init__(self, _pid):
            pass

        def memory_maps(self):
            raise OSError("access changed")

    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(Process=BrokenProcess),
    )

    result = (
        windows_presentation
        ._graphics_module_snapshot(99)
    )

    assert result["pid"] == 99
    assert result["ok"] is False
    assert result["modules"] == []
    assert result["error_type"] == "OSError"


def test_y16_graphics_probe_emits_bounded_stage(
    monkeypatch,
):
    records = []

    monkeypatch.setattr(
        windows_presentation,
        "_graphics_module_snapshot",
        lambda pid: {
            "pid": pid,
            "ok": True,
            "modules": [
                "dxgi.dll",
                "d3d11.dll",
            ],
            "error_type": "",
        },
    )

    monkeypatch.setattr(
        windows_presentation,
        "_helper_diagnostic",
        records.append,
    )

    windows_presentation._DIAGNOSTIC_LAST.clear()

    windows_presentation._probe_graphics_modules(
        {22260}
    )

    assert len(records) == 1
    assert "stage=graphics_modules" in records[0]
    assert "pid=22260" in records[0]
    assert "dxgi.dll" in records[0]
    assert "d3d11.dll" in records[0]


def test_y16_graphics_probe_caps_pid_count(
    monkeypatch,
):
    observed = []

    monkeypatch.setattr(
        windows_presentation,
        "_graphics_module_snapshot",
        lambda pid: (
            observed.append(pid)
            or {
                "pid": pid,
                "ok": True,
                "modules": [],
                "error_type": "",
            }
        ),
    )

    monkeypatch.setattr(
        windows_presentation,
        "_diagnostic_changed",
        lambda *_args, **_kwargs: None,
    )

    windows_presentation._probe_graphics_modules(
        set(range(1, 20))
    )

    assert observed == list(range(1, 9))


def test_y16_source_keeps_diagnostic_probe_out_of_acceptance_contract():
    source = Path(
        windows_presentation.__file__
    ).read_text(encoding="utf-8")

    assert "Q38IU_Y16_GRAPHICS_MODULE_TELEMETRY" in source
    assert "process.memory_maps()" in source
    assert "stage=graphics_modules" in source
    assert "last_graphics_probe" in source
    assert ">= 1.0" in source

    # The Y24B presentation contract remains authoritative.
    assert "timeout: float = 75.0" in source
    assert "default=75.0" in source

    assert 'rejection = "not_visible"' in source
    assert 'rejection = "owned_window"' in source
    assert 'rejection = "window_rect_unavailable"' in source
    assert 'rejection = "window_too_small"' in source

    assert "_resolve_vdd_monitor()" in source
    assert "_verify_window_presentation(" in source
    assert "MonitorFromWindow(" in source
    assert "GetClientRect(" in source
    assert "SetWindowPos(" not in source

    # The graphics probe may observe state but must never introduce
    # an independent success/failure return contract.
    start = source.index(
        "def _probe_graphics_modules("
    )
    end = source.index(
        "\ndef _window_class(",
        start,
    )
    probe = source[start:end]

    assert "return 20" not in probe
    assert "return 21" not in probe
    assert "return 22" not in probe
    assert "return 23" not in probe
    assert "raise WindowsPresentationError" not in probe


def test_y16_module_allowlist_contains_required_boundaries():
    modules = (
        windows_presentation
        ._GRAPHICS_DIAGNOSTIC_MODULES
    )

    required = {
        "dxgi.dll",
        "d3d11.dll",
        "d3d12.dll",
        "d3d9.dll",
        "nvapi64.dll",
        "nvd3dumx.dll",
        "nvwgf2umx.dll",
        "opengl32.dll",
        "vulkan-1.dll",
        "gameoverlayrenderer64.dll",
    }

    assert required.issubset(modules)
