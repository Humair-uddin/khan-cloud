from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import ntpath
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
from typing import Any


# When this file is executed directly inside the managed Windows
# interactive session, add the deployed runtime root so khan_agent
# imports remain deterministic.
if __package__ in (None, ""):
    sys.path.insert(
        0,
        str(Path(__file__).resolve().parents[1]),
    )


VDD_MONITOR_TOKEN = "KHC0001"
VDD_PRESENTATION_ID = r"DISPLAY\KHC0001"

PRESENTATION_WIDTH = 1920
PRESENTATION_HEIGHT = 1080
PRESENTATION_REFRESH_HZ = 60

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000

WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102

MONITOR_DEFAULTTONEAREST = 0x00000002
MONITORINFOF_PRIMARY = 0x00000001
GW_OWNER = 4
UOI_NAME = 2
DESKTOP_READOBJECTS = 0x0001

ENUM_CURRENT_SETTINGS = -1
CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002
CDS_NORESET = 0x10000000
CDS_SET_PRIMARY = 0x00000010
DISP_CHANGE_SUCCESSFUL = 0

DM_POSITION = 0x00000020
DM_BITSPERPEL = 0x00040000
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
_DIAGNOSTIC_CONTEXT: dict[str, Any] = {}
_DIAGNOSTIC_LAST: dict[str, tuple[Any, float]] = {}


def _configure_user32(user32) -> None:
    """Declare the Win32 ABI used by customer presentation."""

    user32.GetMonitorInfoW.argtypes = [
        wintypes.HMONITOR,
        ctypes.c_void_p,
    ]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.LPARAM,
    ]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL

    user32.EnumWindows.argtypes = [
        ctypes.c_void_p,
        wintypes.LPARAM,
    ]
    user32.EnumWindows.restype = wintypes.BOOL

    user32.IsWindowVisible.argtypes = [
        wintypes.HWND,
    ]
    user32.IsWindowVisible.restype = wintypes.BOOL

    user32.GetWindow.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
    ]
    user32.GetWindow.restype = wintypes.HWND

    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    user32.GetWindowRect.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(RECT),
    ]
    user32.GetWindowRect.restype = wintypes.BOOL

    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL

    user32.GetClientRect.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(RECT),
    ]
    user32.GetClientRect.restype = wintypes.BOOL

    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.GetDpiForWindow.restype = wintypes.UINT

    user32.MonitorFromWindow.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
    ]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR

    user32.EnumDisplaySettingsExW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    user32.EnumDisplaySettingsExW.restype = wintypes.BOOL

    user32.ChangeDisplaySettingsExW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    user32.ChangeDisplaySettingsExW.restype = wintypes.LONG


class WindowsPresentationError(RuntimeError):
    """Customer game presentation could not be proven on Khan VDD."""


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


class POINTL(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPosition", POINTL),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", wintypes.SHORT),
        ("dmDuplex", wintypes.SHORT),
        ("dmYResolution", wintypes.SHORT),
        ("dmTTOption", wintypes.SHORT),
        ("dmCollate", wintypes.SHORT),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


def _require_windows() -> None:
    if platform.system() != "Windows":
        raise WindowsPresentationError(
            "Windows customer presentation requires Windows."
        )


def _path_is_within_install_root(
    executable: str,
    install_root: str,
) -> bool:
    executable_n = ntpath.normcase(
        ntpath.normpath(str(executable))
    )
    root_n = ntpath.normcase(
        ntpath.normpath(str(install_root))
    )

    try:
        return (
            ntpath.commonpath([executable_n, root_n])
            == root_n
        )
    except ValueError:
        return False


def _wait_for_helper(
    pid: int,
    *,
    timeout: float,
) -> int:
    kernel32 = ctypes.WinDLL(
        "kernel32",
        use_last_error=True,
    )

    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    kernel32.WaitForSingleObject.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL

    kernel32.TerminateProcess.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
    ]
    kernel32.TerminateProcess.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(
        SYNCHRONIZE
        | PROCESS_QUERY_LIMITED_INFORMATION
        | PROCESS_TERMINATE,
        False,
        int(pid),
    )

    if not handle:
        raise WindowsPresentationError(
            "Unable to open customer-presentation helper."
        )

    try:
        wait_result = kernel32.WaitForSingleObject(
            handle,
            int(max(timeout, 1.0) * 1000),
        )

        if wait_result == WAIT_TIMEOUT:
            try:
                kernel32.TerminateProcess(handle, 124)
            except Exception:
                pass

            raise WindowsPresentationError(
                "Customer-presentation verification timed out."
            )

        if wait_result != WAIT_OBJECT_0:
            raise WindowsPresentationError(
                "Customer-presentation helper wait failed."
            )

        exit_code = wintypes.DWORD()

        if not kernel32.GetExitCodeProcess(
            handle,
            ctypes.byref(exit_code),
        ):
            raise WindowsPresentationError(
                "Unable to read customer-presentation result."
            )

        return int(exit_code.value)

    finally:
        kernel32.CloseHandle(handle)


def ensure_game_on_vdd(
    *,
    install_root: str,
    expected_session_id: int,
    timeout: float = 75.0,
    attempt_id: str = "",
    runtime_id: str = "",
    requested_width: int = PRESENTATION_WIDTH,
    requested_height: int = PRESENTATION_HEIGHT,
    authoritative_pid: int | None = None,
) -> dict[str, Any]:
    """
    Run the presentation verifier inside the already-authorized
    KhanGaming interactive session.

    This helper is transient control-plane machinery. It is deliberately
    not the customer workload ownership root; the D1 Job Object remains
    owned by the Steam/game launch boundary.
    """

    _require_windows()

    root = str(install_root or "").strip()

    if not root:
        raise WindowsPresentationError(
            "Installed game path is unavailable for presentation proof."
        )

    if int(expected_session_id) <= 0:
        raise WindowsPresentationError(
            "Customer presentation requires a non-zero managed session."
        )

    from khan_agent.windows_interactive import (
        InteractiveSessionError,
        launch_in_active_session,
    )

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--helper",
        "--install-root",
        root,
        "--expected-session-id",
        str(int(expected_session_id)),
        "--timeout",
        str(float(timeout)),
        "--attempt-id",
        str(attempt_id or ""),
        "--runtime-id",
        str(runtime_id or ""),
        "--requested-width",
        str(int(requested_width)),
        "--requested-height",
        str(int(requested_height)),
    ]

    if authoritative_pid is not None:
        command.extend(
            [
                "--authoritative-pid",
                str(int(authoritative_pid)),
            ]
        )

    try:
        launched = launch_in_active_session(
            command,
            expected_session_id=int(expected_session_id),
        )
    except InteractiveSessionError as exc:
        raise WindowsPresentationError(
            f"Unable to launch presentation verifier: {exc}"
        ) from exc

    exit_code = _wait_for_helper(
        launched.pid,
        timeout=float(timeout) + 10.0,
    )

    if exit_code != 0:
        reasons = {
            20: "Khan VDD presentation target was not found.",
            21: "No visible game window appeared before timeout.",
            22: "Game window presentation evidence could not be collected.",
            23: "Game window does not satisfy the requested Khan VDD presentation contract.",
            30: "Presentation helper dependency failure.",
        }

        raise WindowsPresentationError(
            reasons.get(
                exit_code,
                f"Presentation helper failed with exit code {exit_code}.",
            )
        )

    return {
        "required": True,
        "verified": True,
        "target_type": "khan_vdd",
        "target_identity": VDD_PRESENTATION_ID,
        "interactive_session_id": int(
            expected_session_id
        ),
        "helper_pid": int(launched.pid),
        "helper_exit_code": exit_code,
        "authoritative_pid": (
            int(authoritative_pid)
            if authoritative_pid is not None
            else None
        ),
        "requested_geometry": {
            "width": int(requested_width),
            "height": int(requested_height),
        },
    }


def _resolve_vdd_device(user32) -> str | None:
    """Resolve the current Windows display name from Khan VDD identity."""
    user32.EnumDisplayDevicesW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(DISPLAY_DEVICEW),
        wintypes.DWORD,
    ]
    user32.EnumDisplayDevicesW.restype = wintypes.BOOL

    adapter_index = 0

    while True:
        adapter = DISPLAY_DEVICEW()
        adapter.cb = ctypes.sizeof(DISPLAY_DEVICEW)

        if not user32.EnumDisplayDevicesW(
            None,
            adapter_index,
            ctypes.byref(adapter),
            0,
        ):
            return None

        monitor_index = 0

        while True:
            monitor = DISPLAY_DEVICEW()
            monitor.cb = ctypes.sizeof(DISPLAY_DEVICEW)

            if not user32.EnumDisplayDevicesW(
                adapter.DeviceName,
                monitor_index,
                ctypes.byref(monitor),
                0,
            ):
                break

            identity = " ".join(
                [
                    str(monitor.DeviceID or ""),
                    str(monitor.DeviceString or ""),
                ]
            ).upper()

            if (
                VDD_MONITOR_TOKEN in identity
                or "KHAN VIRTUAL DISPLAY" in identity
                or "KHANCLOUD VDD" in identity
            ):
                return str(adapter.DeviceName)

            monitor_index += 1

        adapter_index += 1


def _display_topology(user32) -> list[dict[str, Any]]:
    monitors: list[dict[str, Any]] = []

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def callback(hmonitor, _hdc, _rect, _data):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)

        if user32.GetMonitorInfoW(
            hmonitor,
            ctypes.byref(info),
        ):
            monitors.append(
                {
                    "monitor": hmonitor,
                    "device": str(info.szDevice),
                    "left": int(info.rcMonitor.left),
                    "top": int(info.rcMonitor.top),
                    "right": int(info.rcMonitor.right),
                    "bottom": int(info.rcMonitor.bottom),
                    "primary": bool(
                        info.dwFlags
                        & MONITORINFOF_PRIMARY
                    ),
                }
            )

        return True

    callback_ref = MONITORENUMPROC(callback)

    if not user32.EnumDisplayMonitors(
        None,
        None,
        callback_ref,
        0,
    ):
        raise WindowsPresentationError(
            "Unable to enumerate Session-1 monitor geometry."
        )

    return monitors


def _display_mode(user32, device: str, index: int) -> DEVMODEW | None:
    mode = DEVMODEW()
    mode.dmSize = ctypes.sizeof(DEVMODEW)

    if not user32.EnumDisplaySettingsExW(
        device,
        index,
        ctypes.byref(mode),
        0,
    ):
        return None

    return mode


def _display_mode_fact(mode: DEVMODEW | None) -> dict[str, int] | None:
    if mode is None:
        return None

    return {
        "width": int(mode.dmPelsWidth),
        "height": int(mode.dmPelsHeight),
        "refresh_hz": int(mode.dmDisplayFrequency),
        "bits_per_pixel": int(mode.dmBitsPerPel),
        "x": int(mode.dmPosition.x),
        "y": int(mode.dmPosition.y),
    }


def _enumerate_display_modes(
    user32,
    device: str,
) -> list[dict[str, int]]:
    modes: list[dict[str, int]] = []
    index = 0

    while True:
        mode = _display_mode(user32, device, index)

        if mode is None:
            break

        fact = _display_mode_fact(mode)
        if fact is not None:
            modes.append(fact)

        index += 1

    return modes


def _requested_mode(
    current: DEVMODEW,
    *,
    width: int,
    height: int,
    refresh_hz: int,
) -> DEVMODEW:
    requested = DEVMODEW()
    ctypes.memmove(
        ctypes.byref(requested),
        ctypes.byref(current),
        ctypes.sizeof(DEVMODEW),
    )
    requested.dmSize = ctypes.sizeof(DEVMODEW)
    requested.dmPelsWidth = int(width)
    requested.dmPelsHeight = int(height)
    requested.dmDisplayFrequency = int(refresh_hz)
    requested.dmFields = (
        DM_POSITION
        | DM_BITSPERPEL
        | DM_PELSWIDTH
        | DM_PELSHEIGHT
        | DM_DISPLAYFREQUENCY
    )
    return requested


def _ensure_vdd_primary(
    user32,
    *,
    device: str,
    topology: list[dict[str, Any]],
) -> int:
    target = next(
        (
            monitor
            for monitor in topology
            if monitor["device"] == device
        ),
        None,
    )

    if target is None:
        return -1

    if target["primary"]:
        return DISP_CHANGE_SUCCESSFUL

    offset_x = int(target["left"])
    offset_y = int(target["top"])

    ordered = [
        target,
        *(
            monitor
            for monitor in topology
            if monitor is not target
        ),
    ]

    for monitor in ordered:
        current = _display_mode(
            user32,
            str(monitor["device"]),
            ENUM_CURRENT_SETTINGS,
        )

        if current is None:
            return -1

        current.dmFields = DM_POSITION
        current.dmPosition.x = (
            int(monitor["left"]) - offset_x
        )
        current.dmPosition.y = (
            int(monitor["top"]) - offset_y
        )

        flags = CDS_UPDATEREGISTRY | CDS_NORESET

        if monitor is target:
            flags |= CDS_SET_PRIMARY

        result = int(
            user32.ChangeDisplaySettingsExW(
                str(monitor["device"]),
                ctypes.byref(current),
                None,
                flags,
                None,
            )
        )

        if result != DISP_CHANGE_SUCCESSFUL:
            return result

    return int(
        user32.ChangeDisplaySettingsExW(
            None,
            None,
            None,
            0,
            None,
        )
    )


def _establish_vdd_presentation_contract_in_session(
    *,
    width: int,
    height: int,
    refresh_hz: int,
) -> tuple[int, dict[str, Any]]:
    user32 = ctypes.WinDLL(
        "user32",
        use_last_error=True,
    )
    _configure_user32(user32)

    device = _resolve_vdd_device(user32)
    evidence: dict[str, Any] = {
        "device": device,
        "requested": {
            "width": int(width),
            "height": int(height),
            "refresh_hz": int(refresh_hz),
        },
    }

    if not device:
        return 40, evidence

    modes = _enumerate_display_modes(
        user32,
        device,
    )
    evidence["enumerated_mode_count"] = len(modes)
    evidence["requested_mode_enumerated"] = any(
        mode["width"] == int(width)
        and mode["height"] == int(height)
        and mode["refresh_hz"] == int(refresh_hz)
        for mode in modes
    )

    if not evidence["requested_mode_enumerated"]:
        return 41, evidence

    current = _display_mode(
        user32,
        device,
        ENUM_CURRENT_SETTINGS,
    )
    evidence["before_mode"] = _display_mode_fact(current)

    if current is None:
        return 44, evidence

    requested = _requested_mode(
        current,
        width=width,
        height=height,
        refresh_hz=refresh_hz,
    )

    test_result = int(
        user32.ChangeDisplaySettingsExW(
            device,
            ctypes.byref(requested),
            None,
            CDS_TEST,
            None,
        )
    )
    evidence["cds_test_result"] = test_result

    if test_result != DISP_CHANGE_SUCCESSFUL:
        return 42, evidence

    apply_result = int(
        user32.ChangeDisplaySettingsExW(
            device,
            ctypes.byref(requested),
            None,
            CDS_UPDATEREGISTRY,
            None,
        )
    )
    evidence["mode_apply_result"] = apply_result

    if apply_result != DISP_CHANGE_SUCCESSFUL:
        return 43, evidence

    time.sleep(1.0)

    topology = _display_topology(user32)
    primary_result = _ensure_vdd_primary(
        user32,
        device=device,
        topology=topology,
    )
    evidence["primary_apply_result"] = primary_result

    if primary_result != DISP_CHANGE_SUCCESSFUL:
        return 45, evidence

    time.sleep(1.0)

    actual = _display_mode(
        user32,
        device,
        ENUM_CURRENT_SETTINGS,
    )
    evidence["actual_mode"] = _display_mode_fact(actual)

    if (
        actual is None
        or int(actual.dmPelsWidth) != int(width)
        or int(actual.dmPelsHeight) != int(height)
        or int(actual.dmDisplayFrequency)
        != int(refresh_hz)
    ):
        return 44, evidence

    topology = _display_topology(user32)
    target_monitors = [
        monitor
        for monitor in topology
        if monitor["device"] == device
    ]
    primaries = [
        monitor
        for monitor in topology
        if monitor["primary"]
    ]

    evidence["primary_devices"] = [
        monitor["device"]
        for monitor in primaries
    ]

    if (
        len(target_monitors) != 1
        or len(primaries) != 1
        or primaries[0]["device"] != device
    ):
        return 45, evidence

    target = target_monitors[0]
    monitor_width = (
        int(target["right"]) - int(target["left"])
    )
    monitor_height = (
        int(target["bottom"]) - int(target["top"])
    )
    evidence["monitor_geometry"] = {
        "width": monitor_width,
        "height": monitor_height,
    }

    if (
        monitor_width != int(width)
        or monitor_height != int(height)
    ):
        return 46, evidence

    evidence["verified"] = True
    return 0, evidence


def establish_vdd_presentation_contract(
    *,
    expected_session_id: int,
    width: int = PRESENTATION_WIDTH,
    height: int = PRESENTATION_HEIGHT,
    refresh_hz: int = PRESENTATION_REFRESH_HZ,
) -> dict[str, Any]:
    """Establish and verify the Session-1 VDD contract before game launch."""
    _require_windows()

    if int(expected_session_id) <= 0:
        raise WindowsPresentationError(
            "VDD presentation contract requires a non-zero managed session."
        )

    from khan_agent.windows_interactive import (
        InteractiveSessionError,
        launch_in_active_session,
    )

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--prepare-display-contract",
        "--expected-session-id",
        str(int(expected_session_id)),
        "--requested-width",
        str(int(width)),
        "--requested-height",
        str(int(height)),
        "--requested-refresh-hz",
        str(int(refresh_hz)),
    ]

    try:
        launched = launch_in_active_session(
            command,
            expected_session_id=int(expected_session_id),
        )
    except InteractiveSessionError as exc:
        raise WindowsPresentationError(
            "Unable to launch the managed-session VDD contract helper: "
            f"{exc}"
        ) from exc

    exit_code = _wait_for_helper(
        launched.pid,
        timeout=30.0,
    )

    if exit_code != 0:
        reasons = {
            40: "Khan VDD could not be resolved dynamically.",
            41: "Requested VDD presentation mode is not enumerated.",
            42: "CDS_TEST rejected the requested VDD presentation mode.",
            43: "Applying the requested VDD presentation mode failed.",
            44: "Post-apply VDD DEVMODE does not match the requested mode.",
            45: "Khan VDD is not the verified presentation-primary display.",
            46: "Session-1 VDD monitor geometry does not match the requested presentation geometry.",
            47: "VDD presentation-contract helper dependency failure.",
        }
        raise WindowsPresentationError(
            reasons.get(
                exit_code,
                "VDD presentation-contract helper failed "
                f"with exit code {exit_code}.",
            )
        )

    return {
        "required": True,
        "verified": True,
        "target_type": "khan_vdd",
        "target_identity": VDD_PRESENTATION_ID,
        "interactive_session_id": int(expected_session_id),
        "helper_pid": int(launched.pid),
        "helper_exit_code": exit_code,
        "requested_mode": {
            "width": int(width),
            "height": int(height),
            "refresh_hz": int(refresh_hz),
        },
        "actual_mode_verified": True,
        "presentation_primary_verified": True,
        "monitor_geometry_verified": True,
    }


def _resolve_vdd_monitor():
    user32 = ctypes.WinDLL(
        "user32",
        use_last_error=True,
    )
    _configure_user32(user32)

    target_device = _resolve_vdd_device(user32)

    if not target_device:
        return None

    target = next(
        (
            monitor
            for monitor in _display_topology(user32)
            if monitor["device"] == target_device
        ),
        None,
    )

    if target is None:
        return None

    return (
        target["monitor"],
        target["left"],
        target["top"],
        target["right"],
        target["bottom"],
        target_device,
    )


def _game_pids(
    install_root: str,
    expected_session_id: int | None = None,
) -> set[int]:
    try:
        import psutil
    except ImportError:
        raise RuntimeError(
            "psutil unavailable"
        )

    result: set[int] = set()

    for proc in psutil.process_iter(
        ["pid", "exe"]
    ):
        try:
            executable = str(
                proc.info.get("exe") or ""
            )

            if executable and _path_is_within_install_root(
                executable,
                install_root,
            ):
                pid = int(proc.info["pid"])

                if expected_session_id is not None:
                    from khan_agent.windows_verified_process import (
                        read_process_identity,
                    )

                    identity, _ = read_process_identity(
                        pid
                    )

                    if (
                        identity is None
                        or int(identity["session_id"])
                        != int(expected_session_id)
                    ):
                        continue

                result.add(pid)
        except (
            psutil.Error,
            OSError,
            ValueError,
            TypeError,
        ):
            continue

\
    return result


# Q38IU_Y16_GRAPHICS_MODULE_TELEMETRY
#
# Diagnostic only.  This does not participate in process authority,
# presentation acceptance, VDD placement, or launch/readiness decisions.
#
# The probe intentionally records only a small allow-list of module
# basenames.  It never records command lines, arbitrary DLL paths, or
# unrelated process memory-map content.
_GRAPHICS_DIAGNOSTIC_MODULES = frozenset(
    {
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
)


def _graphics_module_snapshot(pid: int) -> dict[str, Any]:
    """Return bounded graphics-module basenames for one live process."""
    result: dict[str, Any] = {
        "pid": int(pid),
        "ok": False,
        "modules": [],
        "error_type": "",
    }

    try:
        import psutil
    except ImportError:
        result["error_type"] = "psutil_unavailable"
        return result

    try:
        process = psutil.Process(int(pid))
        observed: set[str] = set()

        for mapping in process.memory_maps():
            raw_path = str(
                getattr(mapping, "path", "") or ""
            )

            if not raw_path:
                continue

            basename = (
                raw_path
                .replace("\\", "/")
                .rsplit("/", 1)[-1]
                .lower()
            )

            if basename in _GRAPHICS_DIAGNOSTIC_MODULES:
                observed.add(basename)

        result["ok"] = True
        result["modules"] = sorted(observed)
        return result

    except Exception as exc:
        # Best-effort telemetry only.  Access races, process exit, or
        # memory-map query failures must never affect launch behavior.
        result["error_type"] = type(exc).__name__
        return result


def _probe_graphics_modules(pids: set[int]) -> None:
    """Emit rate-limited graphics initialization observations."""
    for pid in sorted(pids)[:8]:
        snapshot = _graphics_module_snapshot(pid)

        modules = tuple(
            str(value)
            for value in snapshot.get("modules", [])
        )
        ok = bool(snapshot.get("ok"))
        error_type = str(
            snapshot.get("error_type") or ""
        )

        _diagnostic_changed(
            f"graphics_modules_{int(pid)}",
            (
                ok,
                modules,
                error_type,
            ),
            lambda pid=pid, ok=ok, modules=modules,
            error_type=error_type: (
                "stage=graphics_modules "
                f"pid={int(pid)} "
                f"ok={ok!r} "
                f"modules={list(modules)!r} "
                f"error_type={error_type!r}"
            ),
        )


def _window_class(user32: Any, hwnd: Any) -> str:
    try:
        user32.GetClassNameW.argtypes = [
            wintypes.HWND, wintypes.LPWSTR, ctypes.c_int,
        ]
        user32.GetClassNameW.restype = ctypes.c_int
        buffer = ctypes.create_unicode_buffer(128)
        if user32.GetClassNameW(hwnd, buffer, len(buffer)):
            return str(buffer.value)[:80]
    except Exception:
        pass
    return ""


def _user_object_name(user32: Any, handle: Any) -> str:
    if not handle:
        return ""
    user32.GetUserObjectInformationW.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
        wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetUserObjectInformationW.restype = wintypes.BOOL
    buffer = ctypes.create_unicode_buffer(256)
    needed = wintypes.DWORD()
    if not user32.GetUserObjectInformationW(
        handle, UOI_NAME, buffer, ctypes.sizeof(buffer), ctypes.byref(needed)
    ):
        raise OSError(ctypes.get_last_error(), "GetUserObjectInformationW")
    return str(buffer.value)[:128]


def _probe_desktop_context(expected_session_id: int | None) -> None:
    """Read desktop identities only; failure never gates presentation."""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.GetProcessWindowStation.restype = wintypes.HANDLE
        user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
        user32.GetThreadDesktop.restype = wintypes.HANDLE
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        station = _user_object_name(user32, user32.GetProcessWindowStation())
        desktop = _user_object_name(
            user32, user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        )
        _DIAGNOSTIC_CONTEXT["helper_desktop"] = desktop
        actual_session = None
        session_error = ""
        try:
            kernel32.ProcessIdToSessionId.argtypes = [
                wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ]
            kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
            session = wintypes.DWORD()
            if kernel32.ProcessIdToSessionId(
                os.getpid(), ctypes.byref(session)
            ):
                actual_session = int(session.value)
            else:
                session_error = str(ctypes.get_last_error())
        except Exception as exc:
            session_error = type(exc).__name__
        input_desktop = ""
        input_error = ""
        try:
            user32.OpenInputDesktop.argtypes = [
                wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
            ]
            user32.OpenInputDesktop.restype = wintypes.HANDLE
            user32.CloseDesktop.argtypes = [wintypes.HANDLE]
            user32.CloseDesktop.restype = wintypes.BOOL
            handle = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
            if handle:
                try:
                    input_desktop = _user_object_name(user32, handle)
                finally:
                    user32.CloseDesktop(handle)
            else:
                input_error = str(ctypes.get_last_error())
        except Exception as exc:
            input_error = type(exc).__name__
        _helper_diagnostic(
            "stage=desktop_context "
            f"expected_session_id={expected_session_id} "
            f"actual_session_id={actual_session} session_error={session_error!r} "
            f"window_station={station!r} helper_desktop={desktop!r} "
            f"input_desktop={input_desktop!r} input_error={input_error!r}"
        )
    except Exception as exc:
        _helper_diagnostic(
            f"stage=desktop_context_error error_type={type(exc).__name__}"
        )


def _probe_other_desktops(pids: set[int]) -> None:
    """Enumerate target GUI-thread desktops read-only, with strict caps."""
    _DIAGNOSTIC_CONTEXT["other_desktop_matches"] = False
    _DIAGNOSTIC_CONTEXT["other_desktop_unresolved"] = False
    if not pids:
        return
    try:
        import psutil
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
        user32.GetThreadDesktop.restype = wintypes.HANDLE
        user32.EnumDesktopWindows.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.LPARAM,
        ]
        user32.EnumDesktopWindows.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        inspected: set[str] = set()
        for pid in sorted(pids)[:8]:
            try:
                threads = psutil.Process(pid).threads()[:24]
            except Exception:
                continue
            for thread in threads:
                try:
                    desktop_handle = user32.GetThreadDesktop(int(thread.id))
                    desktop_name = _user_object_name(user32, desktop_handle)
                    if not desktop_name:
                        _DIAGNOSTIC_CONTEXT["other_desktop_unresolved"] = True
                    if (not desktop_name or
                        desktop_name == _DIAGNOSTIC_CONTEXT.get("helper_desktop") or
                        desktop_name in inspected or len(inspected) >= 4):
                        continue
                    inspected.add(desktop_name)
                    matches: list[dict[str, Any]] = []
                    def callback(hwnd, _data):
                        owner_pid = wintypes.DWORD()
                        tid = user32.GetWindowThreadProcessId(
                            hwnd, ctypes.byref(owner_pid)
                        )
                        if int(owner_pid.value) in pids and len(matches) < 8:
                            matches.append({
                                "hwnd": int(hwnd),
                                "pid": int(owner_pid.value),
                                "tid": int(tid),
                                "class": _window_class(user32, hwnd),
                            })
                        return True
                    ok = bool(user32.EnumDesktopWindows(
                        desktop_handle, callback_type(callback), 0
                    ))
                    if matches:
                        _DIAGNOSTIC_CONTEXT["other_desktop_matches"] = True
                    if not ok:
                        _DIAGNOSTIC_CONTEXT["other_desktop_unresolved"] = True
                    _diagnostic_changed(
                        "other_desktop_" + desktop_name,
                        (ok, tuple((m["hwnd"], m["pid"]) for m in matches)),
                        "stage=other_desktop_scan "
                        f"desktop={desktop_name!r} enum_ok={ok} "
                        f"error={0 if ok else ctypes.get_last_error()} "
                        f"matches={matches!r}",
                    )
                except Exception as exc:
                    _DIAGNOSTIC_CONTEXT["other_desktop_unresolved"] = True
                    _diagnostic_changed(
                        "other_desktop_error", type(exc).__name__,
                        "stage=other_desktop_error "
                        f"error_type={type(exc).__name__}",
                    )
    except Exception as exc:
        _DIAGNOSTIC_CONTEXT["other_desktop_unresolved"] = True
        _diagnostic_changed(
            "other_desktop_api_error", type(exc).__name__,
            f"stage=other_desktop_api_error error_type={type(exc).__name__}",
        )


def _pid_session_relation(pid: int, expected_session_id: int | None) -> str:
    if expected_session_id is None:
        return "unknown"
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.ProcessIdToSessionId.argtypes = [
            wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
        session = wintypes.DWORD()
        if kernel32.ProcessIdToSessionId(pid, ctypes.byref(session)):
            return "expected" if int(session.value) == expected_session_id else "other"
    except Exception:
        pass
    return "unavailable"


def _verified_pid_summary(
    pids: set[int], install_root: str, expected_session_id: int | None,
) -> list[dict[str, Any]]:
    try:
        from khan_agent.windows_verified_process import (
            diagnostic_process_identity, read_process_identity,
        )
        result = []
        for pid in sorted(pids)[:16]:
            identity, _ = read_process_identity(pid)
            if identity is not None:
                fact = diagnostic_process_identity(identity, install_root)
                fact["session_matches"] = (
                    expected_session_id is None or
                    identity.get("session_id") == expected_session_id
                )
                result.append(fact)
        return result
    except Exception as exc:
        return [{"diagnostic_error": type(exc).__name__}]


def _largest_visible_window(
    pids: set[int],
):
    # Q38IU_Y7_TARGET_HWND_TELEMETRY
    #
    # Telemetry only.  The original acceptance contract remains:
    #
    #   target PID
    #   + visible
    #   + unowned
    #   + readable rectangle
    #   + at least 64x64
    #
    # PID is observed first solely so rejected HWNDs belonging to the
    # target game can be diagnosed.  No rejected HWND becomes eligible.
    if not pids:
        _diagnostic_changed(
            "no_target_pids", True,
            "stage=window_scan_skipped reason=no_target_pids",
        )

    user32 = ctypes.WinDLL(
        "user32",
        use_last_error=True,
    )
    _configure_user32(user32)

    windows = []
    target_hwnd_count = 0
    rejected_count = 0
    rejection_reasons: dict[str, int] = {}
    sdl_windows: list[dict[str, Any]] = []
    sdl_count = 0
    alternate_sdl_count = 0
    target_window_log_count = 0

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )

    def callback(hwnd, _data):
        nonlocal target_hwnd_count
        nonlocal rejected_count, sdl_count, alternate_sdl_count
        nonlocal target_window_log_count

        pid = wintypes.DWORD()

        thread_id = user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(pid),
        )

        observed_pid = int(pid.value)
        window_class = _window_class(user32, hwnd)
        if window_class == "SDL_app":
            sdl_count += 1
            if observed_pid not in pids:
                alternate_sdl_count += 1
            if len(sdl_windows) < 8:
                sdl_windows.append({
                    "hwnd": int(hwnd),
                    "pid": observed_pid,
                    "tid": int(thread_id),
                    "class": window_class,
                    "verified_game_pid": observed_pid in pids,
                    "session_relation": _pid_session_relation(
                        observed_pid,
                        _DIAGNOSTIC_CONTEXT.get("expected_session_id"),
                    ),
                })

        if observed_pid not in pids:
            return True

        target_hwnd_count += 1

        visible = bool(
            user32.IsWindowVisible(hwnd)
        )

        owner = user32.GetWindow(
            hwnd,
            GW_OWNER,
        )

        rect = RECT()

        rect_ok = bool(
            user32.GetWindowRect(
                hwnd,
                ctypes.byref(rect),
            )
        )

        if rect_ok:
            left = int(rect.left)
            top = int(rect.top)
            right = int(rect.right)
            bottom = int(rect.bottom)

            width = max(
                0,
                right - left,
            )
            height = max(
                0,
                bottom - top,
            )
        else:
            left = None
            top = None
            right = None
            bottom = None
            width = None
            height = None

        rejection = ""

        # Keep the existing acceptance semantics exactly.
        if not visible:
            rejection = "not_visible"
        elif owner:
            rejection = "owned_window"
        elif not rect_ok:
            rejection = "window_rect_unavailable"
        elif width is None or height is None:
            rejection = "window_geometry_unavailable"
        elif width < 64 or height < 64:
            rejection = "window_too_small"

        accepted = not rejection

        try:
            hwnd_value = int(hwnd)
        except (TypeError, ValueError):
            hwnd_value = 0

        try:
            owner_value = int(owner) if owner else 0
        except (TypeError, ValueError):
            owner_value = 0

        if (
            target_window_log_count < 16
            and _DIAGNOSTIC_CONTEXT.get("window_detail_emitted", 0) < 32
        ):
            target_window_log_count += 1
            _DIAGNOSTIC_CONTEXT["window_detail_emitted"] = (
                _DIAGNOSTIC_CONTEXT.get("window_detail_emitted", 0) + 1
            )
            _diagnostic_changed(
                f"window_observed_{hwnd_value}",
                (
                    observed_pid, visible, owner_value,
                    rect_ok, width, height, rejection,
                ),
                "stage=window_observed "
                f"hwnd={hwnd_value} "
                f"pid={observed_pid} "
                f"tid={int(thread_id)} "
                f"visible={visible!r} "
                f"owner={owner_value} "
                f"rect_ok={rect_ok!r} "
                f"rect={(left, top, right, bottom)!r} "
                f"width={width!r} "
                f"height={height!r} "
                f"accepted={accepted!r} "
                f"rejection={rejection!r}",
            )

        if rejection:
            rejected_count += 1
            rejection_reasons[rejection] = (
                rejection_reasons.get(rejection, 0) + 1
            )
            return True

        windows.append(
            (
                int(width) * int(height),
                hwnd,
                observed_pid,
            )
        )

        return True

    cb = WNDENUMPROC(callback)

    enum_ok = bool(
        user32.EnumWindows(
            cb,
            0,
        )
    )

    enum_error = 0 if enum_ok else ctypes.get_last_error()
    classification = (
        "E_accepted" if windows else
        "D_target_rejected" if target_hwnd_count else
        "C_other_desktop" if _DIAGNOSTIC_CONTEXT.get("other_desktop_matches") else
        "B_alternate_pid_sdl" if alternate_sdl_count else
        "unknown_enum_failure" if not enum_ok else
        "unknown_desktop_probe" if _DIAGNOSTIC_CONTEXT.get(
            "other_desktop_unresolved"
        ) else "A_no_target_gui_hwnd"
    )
    _DIAGNOSTIC_CONTEXT["last_window_classification"] = classification
    summary = (
        classification,
        tuple(sorted(pids)), enum_ok, enum_error, target_hwnd_count,
        tuple(sorted(rejection_reasons.items())), len(windows),
        tuple((w["hwnd"], w["pid"]) for w in sdl_windows),
        sdl_count, alternate_sdl_count,
    )
    _diagnostic_changed(
        "window_scan", summary,
        "stage=window_scan_complete "
        f"classification={classification} "
        f"target_pids={sorted(pids)[:16]!r} "
        f"enum_ok={enum_ok!r} enum_error={enum_error} "
        f"target_pid_hwnd_count={target_hwnd_count} "
        f"rejected_count={rejected_count} "
        f"rejection_reasons={rejection_reasons!r} "
        f"accepted_candidate_count={len(windows)} "
        f"sdl_app_count={sdl_count} alternate_sdl_count={alternate_sdl_count} "
        f"sdl_app_windows={sdl_windows!r}"
    )

    if not windows:
        return None

    windows.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    selected = windows[0]

    try:
        selected_hwnd = int(selected[1])
    except (TypeError, ValueError):
        selected_hwnd = 0

    _diagnostic_changed(
        "window_selected", (selected_hwnd, selected[2]),
        "stage=window_selected "
        f"hwnd={selected_hwnd} "
        f"pid={selected[2]} "
        f"area={selected[0]}"
    )

    return selected[1], selected[2]


def _verify_window_presentation(
    hwnd,
    target,
    *,
    requested_width: int,
    requested_height: int,
) -> tuple[bool, dict[str, Any]]:
    user32 = ctypes.WinDLL(
        "user32",
        use_last_error=True,
    )
    _configure_user32(user32)
    dwmapi = ctypes.WinDLL(
        "dwmapi",
        use_last_error=True,
    )
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    dwmapi.DwmGetWindowAttribute.restype = wintypes.LONG

    (
        target_monitor,
        left,
        top,
        right,
        bottom,
        device_name,
    ) = target

    monitor_width = int(right - left)
    monitor_height = int(bottom - top)
    visible = bool(user32.IsWindowVisible(hwnd))
    iconic = bool(user32.IsIconic(hwnd))

    actual_monitor = user32.MonitorFromWindow(
        hwnd,
        MONITOR_DEFAULTTONEAREST,
    )

    window_rect = RECT()
    window_rect_ok = bool(
        user32.GetWindowRect(
            hwnd,
            ctypes.byref(window_rect),
        )
    )
    client_rect = RECT()
    client_rect_ok = bool(
        user32.GetClientRect(
            hwnd,
            ctypes.byref(client_rect),
        )
    )

    cloaked_value = wintypes.DWORD()
    cloaked_result = int(
        dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            ctypes.byref(cloaked_value),
            ctypes.sizeof(cloaked_value),
        )
    )
    cloaked = (
        int(cloaked_value.value)
        if cloaked_result == 0
        else None
    )

    frame_rect = RECT()
    frame_result = int(
        dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(frame_rect),
            ctypes.sizeof(frame_rect),
        )
    )

    client_width = (
        int(client_rect.right - client_rect.left)
        if client_rect_ok
        else None
    )
    client_height = (
        int(client_rect.bottom - client_rect.top)
        if client_rect_ok
        else None
    )
    evidence = {
        "visible": visible,
        "iconic": iconic,
        "cloaked": cloaked,
        "monitor_matches": bool(
            actual_monitor
            and int(actual_monitor) == int(target_monitor)
        ),
        "monitor_device": device_name,
        "monitor_geometry": {
            "width": monitor_width,
            "height": monitor_height,
        },
        "window_geometry": (
            {
                "left": int(window_rect.left),
                "top": int(window_rect.top),
                "right": int(window_rect.right),
                "bottom": int(window_rect.bottom),
                "width": int(
                    window_rect.right - window_rect.left
                ),
                "height": int(
                    window_rect.bottom - window_rect.top
                ),
            }
            if window_rect_ok
            else None
        ),
        "client_geometry": (
            {
                "width": client_width,
                "height": client_height,
            }
            if client_rect_ok
            else None
        ),
        "dwm_frame_geometry": (
            {
                "left": int(frame_rect.left),
                "top": int(frame_rect.top),
                "right": int(frame_rect.right),
                "bottom": int(frame_rect.bottom),
                "width": int(
                    frame_rect.right - frame_rect.left
                ),
                "height": int(
                    frame_rect.bottom - frame_rect.top
                ),
            }
            if frame_result == 0
            else None
        ),
        "window_dpi": int(user32.GetDpiForWindow(hwnd)),
        "requested_geometry": {
            "width": int(requested_width),
            "height": int(requested_height),
        },
    }

    verified = bool(
        visible
        and not iconic
        and cloaked == 0
        and evidence["monitor_matches"]
        and client_width == int(requested_width)
        and client_height == int(requested_height)
        and monitor_width == int(requested_width)
        and monitor_height == int(requested_height)
    )

    if not verified:
        if not visible:
            evidence["rejection"] = "not_visible"
        elif iconic:
            evidence["rejection"] = "iconic"
        elif cloaked != 0:
            evidence["rejection"] = "cloaked_or_unavailable"
        elif not evidence["monitor_matches"]:
            evidence["rejection"] = "wrong_monitor"
        elif (
            client_width != int(requested_width)
            or client_height != int(requested_height)
        ):
            evidence["rejection"] = "client_geometry_mismatch"
        else:
            evidence["rejection"] = "monitor_geometry_mismatch"

    return verified, evidence


def _helper_diagnostic(message: str) -> None:
    """Best-effort Session-1 presentation diagnostic trace."""
    try:
        path = Path(tempfile.gettempdir()) / (
            "khan-presentation-helper.log"
        )
        now = time.monotonic()
        previous = _DIAGNOSTIC_CONTEXT.get("last_logged", now)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                f"{datetime.now(timezone.utc).isoformat()} "
                f"pid={os.getpid()} "
                f"attempt_id={_DIAGNOSTIC_CONTEXT.get('attempt_id', '')} "
                f"runtime_id={_DIAGNOSTIC_CONTEXT.get('runtime_id', '')} "
                f"monotonic_ms={round(now*1000)} "
                f"elapsed_ms={round((now - _DIAGNOSTIC_CONTEXT.get('started', now))*1000)} "
                f"delta_ms={round((now - previous)*1000)} "
                f"{message}\n"
            )
        _DIAGNOSTIC_CONTEXT["last_logged"] = now
    except Exception:
        pass


def _diagnostic_changed(key: str, value: Any, message: Any) -> None:
    """Emit state changes immediately and an unchanged sample every 5 s."""
    try:
        now = time.monotonic()
        previous = _DIAGNOSTIC_LAST.get(key)
        if previous is None or previous[0] != value or now - previous[1] >= 5.0:
            if key not in _DIAGNOSTIC_LAST and len(_DIAGNOSTIC_LAST) >= 64:
                oldest = min(
                    _DIAGNOSTIC_LAST,
                    key=lambda k: _DIAGNOSTIC_LAST[k][1],
                )
                del _DIAGNOSTIC_LAST[oldest]
            _DIAGNOSTIC_LAST[key] = (value, now)
            _helper_diagnostic(message() if callable(message) else message)
    except Exception as exc:
        _helper_diagnostic(
            f"stage=telemetry_error error_type={type(exc).__name__}"
        )


def _run_helper(
    *,
    install_root: str,
    timeout: float,
    expected_session_id: int | None = None,
    attempt_id: str = "",
    runtime_id: str = "",
    requested_width: int = PRESENTATION_WIDTH,
    requested_height: int = PRESENTATION_HEIGHT,
    authoritative_pid: int | None = None,
) -> int:
    _DIAGNOSTIC_CONTEXT.update(
        attempt_id=str(attempt_id or "")[:80],
        runtime_id=str(runtime_id or "")[:80],
        started=time.monotonic(),
    )
    _DIAGNOSTIC_LAST.clear()
    _DIAGNOSTIC_CONTEXT["expected_session_id"] = expected_session_id
    _DIAGNOSTIC_CONTEXT["window_detail_emitted"] = 0
    _helper_diagnostic("stage=run_helper_enter")
    _probe_desktop_context(expected_session_id)
    if platform.system() != "Windows":
        _helper_diagnostic("stage=platform_not_windows")
        return 30

    try:
        _helper_diagnostic("stage=resolve_vdd_begin")
        target = _resolve_vdd_monitor()
        _helper_diagnostic(
            f"stage=resolve_vdd_complete found={target is not None}"
        )
    except Exception:
        _helper_diagnostic(
            "stage=resolve_vdd_exception "
            + "error_type=probe_failed"
        )
        return 20

    if target is None:
        _helper_diagnostic("stage=resolve_vdd_none")
        return 20

    deadline = time.monotonic() + max(
        5.0,
        float(timeout),
    )

    while time.monotonic() < deadline:
        try:
            pids = _game_pids(
                install_root,
                expected_session_id=(
                    expected_session_id
                    if expected_session_id
                    and expected_session_id > 0
                    else None
                ),
            )
            if authoritative_pid is not None:
                pids = (
                    {int(authoritative_pid)}
                    if int(authoritative_pid) in pids
                    else set()
                )
            # stage=game_pids_begin is represented by the prior
            # runtime/observation transition; emit bounded completed samples.
            _diagnostic_changed(
                "game_pids", tuple(sorted(pids)),
                lambda: (
                    "stage=game_pids_complete "
                    f"pid_count={len(pids)} pids={sorted(pids)[:16]!r} "
                    f"verified_identities={_verified_pid_summary(pids, install_root, expected_session_id)!r}"
                ),
            )
            now = time.monotonic()

            # Graphics initialization is intentionally sampled more
            # frequently than desktop enumeration, but remains bounded.
            # A one-second cadence is sufficient to distinguish the
            # successful ~9-second Y3 initialization from the ~51-53
            # second Y7/Y12 failure signature without continuously
            # walking process memory maps.
            if (
                now
                - _DIAGNOSTIC_CONTEXT.get(
                    "last_graphics_probe",
                    -10.0,
                )
                >= 1.0
            ):
                _DIAGNOSTIC_CONTEXT[
                    "last_graphics_probe"
                ] = now
                _probe_graphics_modules(pids)

            if now - _DIAGNOSTIC_CONTEXT.get("last_desktop_scan", -10.0) >= 5.0:
                _DIAGNOSTIC_CONTEXT["last_desktop_scan"] = now
                _probe_other_desktops(pids)
        except Exception:
            _helper_diagnostic(
                "stage=game_pids_exception "
                + "error_type=probe_failed"
            )
            return 30

        window = _largest_visible_window(
            pids
        )

        if window is None:
            time.sleep(0.4)
            continue

        hwnd, _pid = window

        try:
            _helper_diagnostic(
                "stage=presentation_verification_begin "
                f"pid={int(_pid)} "
                f"hwnd={int(hwnd)}"
            )

            verified, evidence = _verify_window_presentation(
                hwnd,
                target,
                requested_width=int(requested_width),
                requested_height=int(requested_height),
            )
            _helper_diagnostic(
                "stage=presentation_evidence "
                f"pid={int(_pid)} "
                f"hwnd={int(hwnd)} "
                f"evidence={evidence!r}"
            )

            if verified:
                _helper_diagnostic(
                    "stage=presentation_verified "
                    f"pid={int(_pid)} "
                    f"hwnd={int(hwnd)}"
                )
                return 0

            _helper_diagnostic(
                "stage=presentation_not_verified "
                f"pid={int(_pid)} "
                f"hwnd={int(hwnd)}"
            )
            return 23
        except Exception:
            _helper_diagnostic(
                "stage=presentation_exception "
                + "error_type=verification_failed"
            )
            return 22

    _helper_diagnostic(
        "stage=window_wait_timeout "
        "reason=no_accepted_game_window "
        f"classification={_DIAGNOSTIC_CONTEXT.get('last_window_classification', 'unknown')}"
    )
    return 21


def _run_display_contract_helper(
    *,
    expected_session_id: int | None,
    width: int,
    height: int,
    refresh_hz: int,
) -> int:
    _DIAGNOSTIC_CONTEXT.update(
        attempt_id="",
        runtime_id="",
        started=time.monotonic(),
        expected_session_id=expected_session_id,
    )
    _DIAGNOSTIC_LAST.clear()
    _helper_diagnostic(
        "stage=display_contract_enter "
        f"width={int(width)} height={int(height)} "
        f"refresh_hz={int(refresh_hz)}"
    )
    _probe_desktop_context(expected_session_id)

    if platform.system() != "Windows":
        _helper_diagnostic(
            "stage=display_contract_platform_not_windows"
        )
        return 47

    try:
        exit_code, evidence = (
            _establish_vdd_presentation_contract_in_session(
                width=int(width),
                height=int(height),
                refresh_hz=int(refresh_hz),
            )
        )
    except Exception as exc:
        _helper_diagnostic(
            "stage=display_contract_exception "
            f"error_type={type(exc).__name__}"
        )
        return 47

    _helper_diagnostic(
        "stage=display_contract_complete "
        f"exit_code={int(exit_code)} "
        f"evidence={evidence!r}"
    )
    return int(exit_code)


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--helper",
        action="store_true",
    )
    parser.add_argument(
        "--prepare-display-contract",
        action="store_true",
    )
    parser.add_argument(
        "--install-root",
        default="",
    )
    parser.add_argument(
        "--expected-session-id",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=75.0,
    )
    parser.add_argument("--attempt-id", default="")
    parser.add_argument("--runtime-id", default="")
    parser.add_argument(
        "--requested-width",
        type=int,
        default=PRESENTATION_WIDTH,
    )
    parser.add_argument(
        "--requested-height",
        type=int,
        default=PRESENTATION_HEIGHT,
    )
    parser.add_argument(
        "--requested-refresh-hz",
        type=int,
        default=PRESENTATION_REFRESH_HZ,
    )
    parser.add_argument(
        "--authoritative-pid",
        type=int,
        default=0,
    )

    args = parser.parse_args()

    if args.prepare_display_contract:
        return _run_display_contract_helper(
            expected_session_id=(
                args.expected_session_id
                if args.expected_session_id > 0
                else None
            ),
            width=args.requested_width,
            height=args.requested_height,
            refresh_hz=args.requested_refresh_hz,
        )

    if not args.helper:
        return 2

    return _run_helper(
        install_root=args.install_root,
        timeout=args.timeout,
        expected_session_id=(
            args.expected_session_id
            if args.expected_session_id > 0
            else None
        ),
        attempt_id=args.attempt_id,
        runtime_id=args.runtime_id,
        requested_width=args.requested_width,
        requested_height=args.requested_height,
        authoritative_pid=(
            args.authoritative_pid
            if args.authoritative_pid > 0
            else None
        ),
    )


if __name__ == "__main__":
    raise SystemExit(_main())
