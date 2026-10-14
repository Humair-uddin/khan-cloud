from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
from uuid import uuid4

import pytest

from khan_agent import gaming_runtime, windows_presentation


pytestmark = pytest.mark.deployment_safe


DYNAMIC_VDD = r"\\.\DISPLAY42"


def _mode(
    width: int = 1920,
    height: int = 1080,
    refresh_hz: int = 60,
) -> windows_presentation.DEVMODEW:
    mode = windows_presentation.DEVMODEW()
    mode.dmSize = ctypes.sizeof(mode)
    mode.dmBitsPerPel = 32
    mode.dmPelsWidth = width
    mode.dmPelsHeight = height
    mode.dmDisplayFrequency = refresh_hz
    return mode


def _topology(
    *,
    primary: bool = True,
    width: int = 1920,
    height: int = 1080,
):
    return [
        {
            "monitor": 42,
            "device": DYNAMIC_VDD,
            "left": 0,
            "top": 0,
            "right": width,
            "bottom": height,
            "primary": primary,
        },
        {
            "monitor": 7,
            "device": r"\\.\DISPLAY1",
            "left": -1024,
            "top": 0,
            "right": 0,
            "bottom": 768,
            "primary": not primary,
        },
    ]


def _contract_harness(
    monkeypatch,
    *,
    modes=None,
    cds_test_result=0,
    apply_result=0,
    actual_mode=None,
    final_topology=None,
    primary_result=0,
    resolved_device=DYNAMIC_VDD,
):
    calls = []

    class FakeUser32:
        def ChangeDisplaySettingsExW(
            self,
            device,
            mode_pointer,
            _hwnd,
            flags,
            _parameter,
        ):
            requested = None
            if mode_pointer:
                requested = ctypes.cast(
                    mode_pointer,
                    ctypes.POINTER(
                        windows_presentation.DEVMODEW
                    ),
                ).contents
            calls.append(
                {
                    "device": device,
                    "flags": int(flags),
                    "mode": (
                        (
                            int(requested.dmPelsWidth),
                            int(requested.dmPelsHeight),
                            int(requested.dmDisplayFrequency),
                        )
                        if requested is not None
                        else None
                    ),
                }
            )
            if flags == windows_presentation.CDS_TEST:
                return cds_test_result
            return apply_result

    fake_user32 = FakeUser32()
    monkeypatch.setattr(
        windows_presentation.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: fake_user32,
        raising=False,
    )
    monkeypatch.setattr(
        windows_presentation,
        "_configure_user32",
        lambda _user32: None,
    )
    monkeypatch.setattr(
        windows_presentation,
        "_resolve_vdd_device",
        lambda _user32: resolved_device,
    )
    monkeypatch.setattr(
        windows_presentation,
        "_enumerate_display_modes",
        lambda _user32, _device: (
            modes
            if modes is not None
            else [
                {
                    "width": 1920,
                    "height": 1080,
                    "refresh_hz": 60,
                    "bits_per_pixel": 32,
                    "x": 0,
                    "y": 0,
                },
                {
                    "width": 1920,
                    "height": 1080,
                    "refresh_hz": 120,
                    "bits_per_pixel": 32,
                    "x": 0,
                    "y": 0,
                },
            ]
        ),
    )

    mode_reads = iter(
        [
            _mode(),
            actual_mode if actual_mode is not None else _mode(),
        ]
    )
    monkeypatch.setattr(
        windows_presentation,
        "_display_mode",
        lambda *_args, **_kwargs: next(mode_reads),
    )

    topologies = iter(
        [
            _topology(),
            (
                final_topology
                if final_topology is not None
                else _topology()
            ),
        ]
    )
    monkeypatch.setattr(
        windows_presentation,
        "_display_topology",
        lambda _user32: next(topologies),
    )
    monkeypatch.setattr(
        windows_presentation,
        "_ensure_vdd_primary",
        lambda *_args, **_kwargs: primary_result,
    )
    monkeypatch.setattr(
        windows_presentation.time,
        "sleep",
        lambda _seconds: None,
    )

    exit_code, evidence = (
        windows_presentation
        ._establish_vdd_presentation_contract_in_session(
            width=1920,
            height=1080,
            refresh_hz=60,
        )
    )
    return exit_code, evidence, calls


def test_dynamic_vdd_mode_is_tested_applied_and_verified(monkeypatch):
    exit_code, evidence, calls = _contract_harness(
        monkeypatch
    )

    assert exit_code == 0
    assert evidence["device"] == DYNAMIC_VDD
    assert evidence["verified"] is True
    assert evidence["actual_mode"] == {
        "width": 1920,
        "height": 1080,
        "refresh_hz": 60,
        "bits_per_pixel": 32,
        "x": 0,
        "y": 0,
    }
    assert [call["flags"] for call in calls] == [
        windows_presentation.CDS_TEST,
        windows_presentation.CDS_UPDATEREGISTRY,
    ]
    assert all(
        call["device"] == DYNAMIC_VDD
        for call in calls
    )
    assert all(
        call["mode"] == (1920, 1080, 60)
        for call in calls
    )
    assert "DISPLAY6" not in Path(
        windows_presentation.__file__
    ).read_text(encoding="utf-8")


def test_requested_mode_missing_fails_before_cds_test(monkeypatch):
    exit_code, evidence, calls = _contract_harness(
        monkeypatch,
        modes=[
            {
                "width": 3840,
                "height": 2160,
                "refresh_hz": 60,
            }
        ],
    )

    assert exit_code == 41
    assert evidence["requested_mode_enumerated"] is False
    assert calls == []


def test_unresolved_vdd_fails_before_mode_enumeration(
    monkeypatch,
):
    exit_code, evidence, calls = _contract_harness(
        monkeypatch,
        resolved_device=None,
    )

    assert exit_code == 40
    assert evidence["device"] is None
    assert calls == []


def test_cds_test_rejection_fails_closed(monkeypatch):
    exit_code, evidence, calls = _contract_harness(
        monkeypatch,
        cds_test_result=-2,
    )

    assert exit_code == 42
    assert evidence["cds_test_result"] == -2
    assert len(calls) == 1


def test_mode_application_failure_fails_closed(monkeypatch):
    exit_code, evidence, calls = _contract_harness(
        monkeypatch,
        apply_result=-1,
    )

    assert exit_code == 43
    assert evidence["mode_apply_result"] == -1
    assert len(calls) == 2


def test_post_apply_devmode_mismatch_fails_closed(monkeypatch):
    exit_code, evidence, _calls = _contract_harness(
        monkeypatch,
        actual_mode=_mode(3840, 2160, 60),
    )

    assert exit_code == 44
    assert evidence["actual_mode"]["width"] == 3840


def test_vdd_not_presentation_primary_fails_closed(monkeypatch):
    exit_code, evidence, _calls = _contract_harness(
        monkeypatch,
        final_topology=_topology(primary=False),
    )

    assert exit_code == 45
    assert evidence["primary_devices"] == [
        r"\\.\DISPLAY1"
    ]


def test_post_apply_monitor_geometry_mismatch_fails_closed(
    monkeypatch,
):
    exit_code, evidence, _calls = _contract_harness(
        monkeypatch,
        final_topology=_topology(
            width=960,
            height=540,
        ),
    )

    assert exit_code == 46
    assert evidence["monitor_geometry"] == {
        "width": 960,
        "height": 540,
    }


def _window_evidence(
    monkeypatch,
    *,
    client=(1920, 1080),
    actual_monitor=42,
    visible=True,
    iconic=False,
    cloaked=0,
):
    class FakeUser32:
        def IsWindowVisible(self, _hwnd):
            return visible

        def IsIconic(self, _hwnd):
            return iconic

        def MonitorFromWindow(self, _hwnd, _flags):
            return actual_monitor

        def GetWindowRect(self, _hwnd, pointer):
            rect = ctypes.cast(
                pointer,
                ctypes.POINTER(windows_presentation.RECT),
            ).contents
            rect.left = 0
            rect.top = 0
            rect.right = 1920
            rect.bottom = 1080
            return 1

        def GetClientRect(self, _hwnd, pointer):
            rect = ctypes.cast(
                pointer,
                ctypes.POINTER(windows_presentation.RECT),
            ).contents
            rect.left = 0
            rect.top = 0
            rect.right = client[0]
            rect.bottom = client[1]
            return 1

        def GetDpiForWindow(self, _hwnd):
            return 96

    def dwm_get_window_attribute(
            _hwnd,
            attribute,
            pointer,
            _size,
    ):
        if attribute == windows_presentation.DWMWA_CLOAKED:
            value = ctypes.cast(
                pointer,
                ctypes.POINTER(wintypes.DWORD),
            ).contents
            value.value = cloaked
        else:
            rect = ctypes.cast(
                pointer,
                ctypes.POINTER(
                    windows_presentation.RECT
                ),
            ).contents
            rect.left = 0
            rect.top = 0
            rect.right = 1920
            rect.bottom = 1080
        return 0

    class Function:
        def __init__(self, function):
            self.function = function

        def __call__(self, *args):
            return self.function(*args)

    class FakeDwm:
        DwmGetWindowAttribute = Function(
            dwm_get_window_attribute
        )

    user32 = FakeUser32()
    dwmapi = FakeDwm()
    monkeypatch.setattr(
        windows_presentation.ctypes,
        "WinDLL",
        lambda name, **_kwargs: (
            user32 if name == "user32" else dwmapi
        ),
        raising=False,
    )
    monkeypatch.setattr(
        windows_presentation,
        "_configure_user32",
        lambda _user32: None,
    )

    return windows_presentation._verify_window_presentation(
        99,
        (42, 0, 0, 1920, 1080, DYNAMIC_VDD),
        requested_width=1920,
        requested_height=1080,
    )


def test_game_presentation_accepts_exact_visible_vdd_client(
    monkeypatch,
):
    verified, evidence = _window_evidence(monkeypatch)

    assert verified is True
    assert evidence["visible"] is True
    assert evidence["iconic"] is False
    assert evidence["cloaked"] == 0
    assert evidence["monitor_matches"] is True
    assert evidence["client_geometry"] == {
        "width": 1920,
        "height": 1080,
    }
    assert evidence["window_dpi"] == 96


def test_game_presentation_rejects_half_size_client(monkeypatch):
    verified, evidence = _window_evidence(
        monkeypatch,
        client=(960, 540),
    )

    assert verified is False
    assert evidence["rejection"] == (
        "client_geometry_mismatch"
    )


def test_game_presentation_rejects_physical_monitor(monkeypatch):
    verified, evidence = _window_evidence(
        monkeypatch,
        actual_monitor=7,
    )

    assert verified is False
    assert evidence["rejection"] == "wrong_monitor"


def test_display_contract_failure_blocks_before_game_preparation(
    tmp_path,
    monkeypatch,
):
    prepare_calls = []

    monkeypatch.setattr(
        gaming_runtime,
        "_validate_windows_native",
        lambda **_kwargs: {
            "gpu": {
                "available": True,
                "memory_total_mib": 12288,
            }
        },
    )
    monkeypatch.setattr(
        gaming_runtime,
        "_interactive_session_context",
        lambda: {
            "required": True,
            "validated": True,
            "session_id": 1,
            "execution_context": "interactive_user",
        },
    )
    monkeypatch.setattr(
        gaming_runtime,
        "_establish_presentation_contract",
        lambda _session: (_ for _ in ()).throw(
            gaming_runtime.GamingRuntimeError(
                "requested mode not enumerated"
            )
        ),
    )
    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        lambda _payload: prepare_calls.append(True),
    )

    result = gaming_runtime.create_session(
        {
            "session_id": str(uuid4()),
            "gpu_uuid": "GPU-Y24B",
            "minimum_vram_mb": 8192,
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
    )

    assert result.status == "blocked"
    assert "requested mode not enumerated" in (
        result.error_message
    )
    assert prepare_calls == []


def test_primary_transaction_preserves_other_monitor_resolution(
    monkeypatch,
):
    calls = []
    modes = {
        DYNAMIC_VDD: _mode(1920, 1080, 60),
        r"\\.\DISPLAY1": _mode(1024, 768, 60),
    }

    class FakeUser32:
        def ChangeDisplaySettingsExW(
            self,
            device,
            mode_pointer,
            _hwnd,
            flags,
            _parameter,
        ):
            mode = (
                ctypes.cast(
                    mode_pointer,
                    ctypes.POINTER(
                        windows_presentation.DEVMODEW
                    ),
                ).contents
                if mode_pointer
                else None
            )
            calls.append(
                (
                    device,
                    int(flags),
                    (
                        int(mode.dmPosition.x),
                        int(mode.dmPosition.y),
                        int(mode.dmFields),
                    )
                    if mode is not None
                    else None,
                )
            )
            return 0

    monkeypatch.setattr(
        windows_presentation,
        "_display_mode",
        lambda _user32, device, _index: modes[device],
    )

    result = windows_presentation._ensure_vdd_primary(
        FakeUser32(),
        device=DYNAMIC_VDD,
        topology=[
            {
                "monitor": 42,
                "device": DYNAMIC_VDD,
                "left": 1024,
                "top": 0,
                "right": 2944,
                "bottom": 1080,
                "primary": False,
            },
            {
                "monitor": 7,
                "device": r"\\.\DISPLAY1",
                "left": 0,
                "top": 0,
                "right": 1024,
                "bottom": 768,
                "primary": True,
            },
        ],
    )

    assert result == 0
    assert calls[0][0] == DYNAMIC_VDD
    assert (
        calls[0][1]
        & windows_presentation.CDS_SET_PRIMARY
    )
    assert calls[0][2] == (
        0,
        0,
        windows_presentation.DM_POSITION,
    )
    assert calls[1][0] == r"\\.\DISPLAY1"
    assert calls[1][2] == (
        -1024,
        0,
        windows_presentation.DM_POSITION,
    )
    assert calls[2] == (None, 0, None)
