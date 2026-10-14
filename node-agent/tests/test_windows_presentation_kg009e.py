from __future__ import annotations

from pathlib import Path

import pytest

from khan_agent import (
    gaming_launchers,
    gaming_runtime,
    windows_presentation,
)


def test_windows_path_membership_is_case_insensitive():
    assert windows_presentation._path_is_within_install_root(
        r"C:\Games\CS2\game\bin\win64\cs2.exe",
        r"c:\games\cs2",
    )

    assert not windows_presentation._path_is_within_install_root(
        r"C:\Games\Other\other.exe",
        r"C:\Games\CS2",
    )


def test_managed_windows_launch_records_verified_vdd_presentation(
    monkeypatch,
):
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={
            "app_id": "730",
            "install_path": r"C:\SteamLibrary\steamapps\common\CS2",
        },
        launcher_executable=r"C:\Steam\steam.exe",
        runtime_id="kc-gaming-test",
        expected_session_id=7,
    )

    adapter = gaming_launchers._ADAPTERS["steam"]

    monkeypatch.setattr(
        gaming_launchers.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        adapter,
        "launch",
        lambda _prepared: {
            "launcher_type": "steam",
            "launcher_game_id": "730",
            "launcher_pid": 4242,
            "runtime_ownership": {
                "schema_version": 2,
                "ownership_type": "windows_job_object",
                "boundary_established": True,
            },
        },
    )

    presentation_call = {}

    def ensure_game_on_vdd(**kwargs):
        presentation_call.update(kwargs)
        return {
            "required": True,
            "verified": True,
            "target_type": "khan_vdd",
            "target_identity": r"DISPLAY\KHC0001",
            "interactive_session_id":
                kwargs["expected_session_id"],
        }

    monkeypatch.setattr(
        windows_presentation,
        "ensure_game_on_vdd",
        ensure_game_on_vdd,
    )

    result = gaming_launchers.launch_prepared_game(
        prepared
    )

    assert result["launcher_pid"] == 4242
    assert result["presentation"]["required"] is True
    assert result["presentation"]["verified"] is True
    assert (
        result["presentation"]["target_identity"]
        == r"DISPLAY\KHC0001"
    )
    assert presentation_call["authoritative_pid"] == 4242


def test_presentation_failure_preserves_launch_and_ownership_metadata(
    monkeypatch,
):
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={
            "app_id": "730",
            "install_path": r"C:\SteamLibrary\steamapps\common\CS2",
        },
        launcher_executable=r"C:\Steam\steam.exe",
        runtime_id="kc-gaming-test",
        expected_session_id=7,
    )

    adapter = gaming_launchers._ADAPTERS["steam"]

    monkeypatch.setattr(
        gaming_launchers.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        adapter,
        "launch",
        lambda _prepared: {
            "launcher_pid": 4242,
            "runtime_ownership": {
                "schema_version": 2,
                "ownership_type": "windows_job_object",
                "job_name": "Global\\KhanCloudGaming_test",
                "boundary_established": True,
            },
        },
    )

    def fail(**_kwargs):
        raise windows_presentation.WindowsPresentationError(
            "test failure"
        )

    monkeypatch.setattr(
        windows_presentation,
        "ensure_game_on_vdd",
        fail,
    )

    result = gaming_launchers.launch_prepared_game(
        prepared
    )

    assert result["launcher_pid"] == 4242
    assert (
        result["runtime_ownership"]["boundary_established"]
        is True
    )
    assert result["presentation"]["required"] is True
    assert result["presentation"]["verified"] is False
    assert result["presentation"]["error"] == "test failure"


def test_stream_readiness_contract_fails_closed_on_unverified_presentation():
    source = Path(
        gaming_runtime.__file__
    ).read_text(
        encoding="utf-8"
    )

    function = source.index(
        "def _verify_stream_readiness("
    )
    presentation = source.index(
        'presentation = launch_info.get(',
        function,
    )
    verified = source.index(
        'presentation.get("verified")',
        presentation,
    )
    launcher = source.index(
        "launcher_pid = None",
        verified,
    )

    assert (
        function
        < presentation
        < verified
        < launcher
    )


def test_windows_presentation_does_not_hardcode_display_number_or_geometry():
    source = Path(
        windows_presentation.__file__
    ).read_text(
        encoding="utf-8"
    )

    assert r"DISPLAY6" not in source
    assert "1024, 0" not in source
    assert "1920x1080" not in source
    assert "3840x2160" not in source

    assert "KHC0001" in source
    assert "EnumDisplayDevicesW" in source
    assert "EnumDisplayMonitors" in source


def test_low_level_interactive_security_boundary_remains_unchanged():
    source = Path(
        Path(
            gaming_launchers.__file__
        ).with_name(
            "windows_interactive.py"
        )
    ).read_text(
        encoding="utf-8"
    )

    assert "CREATE_SUSPENDED" in source
    assert "AssignProcessToJobObject" in source
    assert "ResumeThread(thread_handle)" in source


def test_windows_presentation_declares_pointer_safe_user32_abi():
    source = Path(
        windows_presentation.__file__
    ).read_text(
        encoding="utf-8"
    )

    assert "def _configure_user32(user32)" in source

    required = [
        "GetMonitorInfoW.argtypes",
        "GetMonitorInfoW.restype",
        "EnumDisplayMonitors.argtypes",
        "EnumDisplayMonitors.restype",
        "EnumWindows.argtypes",
        "EnumWindows.restype",
        "GetWindow.argtypes",
        "GetWindow.restype = wintypes.HWND",
        "GetWindowThreadProcessId.argtypes",
        "GetWindowRect.argtypes",
        "GetClientRect.argtypes",
        "IsIconic.argtypes",
        "GetDpiForWindow.argtypes",
        "MonitorFromWindow.argtypes",
        "MonitorFromWindow.restype = wintypes.HMONITOR",
        "EnumDisplaySettingsExW.argtypes",
        "ChangeDisplaySettingsExW.argtypes",
    ]

    for declaration in required:
        assert declaration in source

    # Every user32 instance used by presentation must be configured
    # before its Win32 calls are made.
    assert source.count(
        "\n    _configure_user32(user32)"
    ) >= 4


def test_presentation_helper_has_durable_stage_diagnostics():
    source = Path(
        windows_presentation.__file__
    ).read_text(
        encoding="utf-8"
    )

    assert "def _helper_diagnostic(message: str)" in source
    assert "khan-presentation-helper.log" in source
    assert "stage=run_helper_enter" in source
    assert "stage=resolve_vdd_begin" in source
    assert "stage=resolve_vdd_complete" in source
    assert "stage=resolve_vdd_exception" in source
    assert "stage=game_pids_begin" in source
    assert "stage=game_pids_complete" in source
    assert "stage=game_pids_exception" in source



def test_q38iu_y7_target_hwnd_telemetry_preserves_filter_contract():
    source = Path(
        windows_presentation.__file__
    ).read_text(
        encoding="utf-8"
    )

    start = source.index(
        "def _largest_visible_window("
    )
    end = source.index(
        "\ndef _verify_window_presentation(",
        start,
    )

    function = source[start:end]

    assert "Q38IU_Y7_TARGET_HWND_TELEMETRY" in function

    # PID must now be observed before visibility filtering so an
    # invisible HWND owned by the target game can be diagnosed.
    pid_read = function.index(
        "GetWindowThreadProcessId("
    )
    pid_filter = function.index(
        "if observed_pid not in pids:"
    )
    visibility = function.index(
        "IsWindowVisible(hwnd)"
    )

    assert (
        pid_read
        < pid_filter
        < visibility
    )

    # Existing acceptance gates remain present and fail closed.
    assert 'rejection = "not_visible"' in function
    assert 'rejection = "owned_window"' in function
    assert (
        'rejection = "window_rect_unavailable"'
        in function
    )
    assert (
        'rejection = "window_too_small"'
        in function
    )
    assert "width < 64 or height < 64" in function

    # Rejected target HWNDs must return from the callback before
    # candidate insertion.
    reject_return = function.index(
        "if rejection:"
    )
    append_candidate = function.index(
        "        windows.append("
    )

    assert reject_return < append_candidate

    # Diagnostic evidence includes both per-HWND observations and
    # an explicit zero/accepted-candidate scan summary.
    assert "stage=window_observed" in function
    assert "rejection={rejection!r}" in function
    assert "stage=window_scan_complete" in function
    assert "target_pid_hwnd_count=" in function
    assert "accepted_candidate_count=" in function


def test_q38iu_y7_does_not_change_presentation_deadline_or_exit_contract():
    source = Path(
        windows_presentation.__file__
    ).read_text(
        encoding="utf-8"
    )

    assert "timeout: float = 75.0" in source
    assert 'default=75.0' in source

    assert "return 20" in source
    assert "return 21" in source
    assert "return 22" in source
    assert "return 23" in source
    assert "return 30" in source
    assert "return 0" in source

    assert "stage=window_wait_timeout" in source
    assert "reason=no_accepted_game_window" in source


def test_q38iu_y24b_verifies_native_vdd_presentation_without_moving_window():
    source = Path(
        windows_presentation.__file__
    ).read_text(
        encoding="utf-8"
    )

    assert "_resolve_vdd_monitor()" in source
    assert "_verify_window_presentation(" in source
    assert "MonitorFromWindow(" in source
    assert "MONITOR_DEFAULTTONEAREST" in source
    assert "GetClientRect(" in source
    assert "DwmGetWindowAttribute(" in source
    assert "SetWindowPos(" not in source

    # The initial resolution contract is explicit, but display numbering
    # and topology remain dynamically resolved.
    assert r"DISPLAY6" not in source
    assert "1024, 0" not in source
    assert "3840x2160" not in source


def _scan_windows(monkeypatch, pids, windows, *, other_desktop=False):
    import ctypes
    from ctypes import wintypes

    observed = []
    class Fn:
        def __init__(self, fn):
            self.fn = fn
        def __call__(self, *args):
            return self.fn(*args)

    by_hwnd = {item["hwnd"]: item for item in windows}
    class User32:
        def __getattr__(self, _name):
            return Fn(lambda *_args: 1)

    user32 = User32()
    def enum_windows(callback, _data):
        for item in windows:
            callback(item["hwnd"], 0)
        return 1
    def owner_thread(hwnd, pid_pointer):
        item = by_hwnd[hwnd]
        ctypes.cast(pid_pointer, ctypes.POINTER(wintypes.DWORD)).contents.value = item["pid"]
        return item.get("tid", 123)
    def get_rect(hwnd, rect_pointer):
        item = by_hwnd[hwnd]
        if not item.get("rect_ok", True):
            return 0
        rect = ctypes.cast(rect_pointer, ctypes.POINTER(windows_presentation.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = item.get("rect", (0, 0, 800, 600))
        return 1
    def get_class(hwnd, buffer, _length):
        buffer.value = by_hwnd[hwnd].get("class", "Other")
        return len(buffer.value)
    user32.EnumWindows = Fn(enum_windows)
    user32.GetWindowThreadProcessId = Fn(owner_thread)
    user32.GetWindowRect = Fn(get_rect)
    user32.GetClassNameW = Fn(get_class)
    user32.IsWindowVisible = Fn(lambda hwnd: by_hwnd[hwnd].get("visible", True))
    user32.GetWindow = Fn(lambda hwnd, _kind: by_hwnd[hwnd].get("owner", 0))
    monkeypatch.setattr(windows_presentation.ctypes, "WinDLL",
                        lambda *_args, **_kwargs: user32, raising=False)
    monkeypatch.setattr(windows_presentation.ctypes, "WINFUNCTYPE",
                        lambda *_args: lambda callback: callback, raising=False)
    monkeypatch.setattr(windows_presentation, "_helper_diagnostic", observed.append)
    windows_presentation._DIAGNOSTIC_LAST.clear()
    windows_presentation._DIAGNOSTIC_CONTEXT["other_desktop_matches"] = other_desktop
    windows_presentation._DIAGNOSTIC_CONTEXT["other_desktop_unresolved"] = False
    windows_presentation._DIAGNOSTIC_CONTEXT["expected_session_id"] = None
    windows_presentation._DIAGNOSTIC_CONTEXT["window_detail_emitted"] = 0
    result = windows_presentation._largest_visible_window(set(pids))
    return result, observed


@pytest.mark.parametrize(
    "pids,windows,other_desktop,expected_class,accepted",
    [
        (set(), [], False, "A_no_target_gui_hwnd", False),
        ({10}, [{"hwnd": 1, "pid": 20, "class": "SDL_app"}],
         False, "B_alternate_pid_sdl", False),
        ({10}, [], True, "C_other_desktop", False),
        ({10}, [{"hwnd": 2, "pid": 10, "visible": False}],
         False, "D_target_rejected", False),
        ({10}, [{"hwnd": 3, "pid": 10, "class": "SDL_app"}],
         False, "E_accepted", True),
    ],
)
def test_y9_window_classification_preserves_acceptance(
    monkeypatch, pids, windows, other_desktop, expected_class, accepted,
):
    result, records = _scan_windows(
        monkeypatch, pids, windows, other_desktop=other_desktop,
    )
    assert (result is not None) is accepted
    assert any(f"classification={expected_class}" in r for r in records)
    if expected_class == "B_alternate_pid_sdl":
        assert any("sdl_app_count=1" in r and "'pid': 20" in r for r in records)
    if expected_class == "D_target_rejected":
        assert any("rejection='not_visible'" in r for r in records)


def test_y9_window_sampling_is_bounded_and_omits_titles(monkeypatch):
    windows = [{"hwnd": 5, "pid": 10, "class": "SDL_app", "title": "secret"}]
    first, records = _scan_windows(monkeypatch, {10}, windows)
    assert first == (5, 10)
    for _ in range(20):
        windows_presentation._largest_visible_window({10})
    assert len(records) <= 4
    assert all("secret" not in record for record in records)


def test_y9_desktop_api_failure_is_diagnostic(monkeypatch):
    records = []
    monkeypatch.setattr(
        windows_presentation.ctypes, "WinDLL",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("denied")),
        raising=False,
    )
    monkeypatch.setattr(windows_presentation, "_helper_diagnostic", records.append)
    windows_presentation._probe_desktop_context(1)
    assert any("stage=desktop_context_error" in r for r in records)


def test_y9_other_desktop_enumeration_is_read_only_and_reports_match(
    monkeypatch,
):
    import ctypes
    import sys
    from ctypes import wintypes
    from types import SimpleNamespace

    records = []
    class Fn:
        def __init__(self, fn):
            self.fn = fn
        def __call__(self, *args):
            return self.fn(*args)
    class User32:
        GetThreadDesktop = Fn(lambda _tid: 77)
        EnumDesktopWindows = Fn(lambda _desktop, callback, _data: callback(9, 0))
        GetWindowThreadProcessId = Fn(
            lambda _hwnd, pointer: (
                setattr(
                    ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents,
                    "value", 10,
                ) or 42
            )
        )
    fake_psutil = SimpleNamespace(
        Process=lambda _pid: SimpleNamespace(
            threads=lambda: [SimpleNamespace(id=42)]
        )
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    monkeypatch.setattr(windows_presentation.ctypes, "WinDLL",
                        lambda *_args, **_kwargs: User32(), raising=False)
    monkeypatch.setattr(windows_presentation.ctypes, "WINFUNCTYPE",
                        lambda *_args: lambda callback: callback, raising=False)
    monkeypatch.setattr(windows_presentation, "_user_object_name",
                        lambda _user32, _handle: "OtherDesktop")
    monkeypatch.setattr(windows_presentation, "_window_class",
                        lambda _user32, _hwnd: "SDL_app")
    monkeypatch.setattr(windows_presentation, "_helper_diagnostic", records.append)
    windows_presentation._DIAGNOSTIC_CONTEXT["helper_desktop"] = "Default"
    windows_presentation._DIAGNOSTIC_LAST.clear()
    windows_presentation._probe_other_desktops({10})
    assert windows_presentation._DIAGNOSTIC_CONTEXT["other_desktop_matches"] is True
    assert any("stage=other_desktop_scan" in r and "'hwnd': 9" in r
               for r in records)


def test_y9_rate_limiter_api_failure_is_diagnostic(monkeypatch):
    records = []
    monkeypatch.setattr(windows_presentation, "_helper_diagnostic", records.append)
    monkeypatch.setattr(
        windows_presentation.time, "monotonic",
        lambda: (_ for _ in ()).throw(OSError("clock unavailable")),
    )
    windows_presentation._diagnostic_changed("probe", 1, "sample")
    assert any("stage=telemetry_error" in r for r in records)


def test_y9_failed_desktop_probe_does_not_claim_absent_hwnd(monkeypatch):
    result, records = _scan_windows(monkeypatch, {10}, [])
    assert result is None
    windows_presentation._DIAGNOSTIC_CONTEXT["other_desktop_unresolved"] = True
    windows_presentation._DIAGNOSTIC_LAST.clear()
    result = windows_presentation._largest_visible_window({10})
    assert result is None
    assert any("classification=unknown_desktop_probe" in r for r in records)


def test_y9_target_window_detail_has_per_scan_and_helper_caps(monkeypatch):
    windows = [{"hwnd": n, "pid": 10} for n in range(1, 101)]
    result, records = _scan_windows(monkeypatch, {10}, windows)
    assert result is not None
    assert sum("stage=window_observed" in r for r in records) == 16
    assert windows_presentation._DIAGNOSTIC_CONTEXT["window_detail_emitted"] == 16
    assert '< 32' in Path(windows_presentation.__file__).read_text()
