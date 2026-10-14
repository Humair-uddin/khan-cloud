from __future__ import annotations

import ctypes
from ctypes import wintypes
import ntpath
import platform
import time
from typing import Any

from khan_agent.launch_diagnostics import LaunchTrace


PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000

WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102


class WindowsVerifiedProcessError(RuntimeError):
    """A durable Windows workload identity could not be proven safely."""


def _require_windows() -> None:
    if platform.system() != "Windows":
        raise WindowsVerifiedProcessError(
            "Verified Windows process ownership requires Windows."
        )


def _norm(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(path or "")))


def path_is_within_install_root(
    executable: str,
    install_root: str,
) -> bool:
    executable_n = _norm(executable)
    root_n = _norm(install_root)

    if not executable_n or not root_n:
        return False

    try:
        return ntpath.commonpath(
            [executable_n, root_n]
        ) == root_n
    except ValueError:
        return False


def _kernel32():
    _require_windows()
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _filetime_value(value: wintypes.FILETIME) -> int:
    return (
        (int(value.dwHighDateTime) << 32)
        | int(value.dwLowDateTime)
    )


def _read_identity_from_handle(
    handle: int,
    pid: int,
) -> dict[str, Any]:
    kernel32 = _kernel32()

    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL

    kernel32.ProcessIdToSessionId.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.ProcessIdToSessionId.restype = wintypes.BOOL

    capacity = 32768
    buffer = ctypes.create_unicode_buffer(capacity)
    size = wintypes.DWORD(capacity)

    if not kernel32.QueryFullProcessImageNameW(
        handle,
        0,
        buffer,
        ctypes.byref(size),
    ):
        raise WindowsVerifiedProcessError(
            "QueryFullProcessImageNameW failed: "
            f"WinError {ctypes.get_last_error()}"
        )

    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()

    if not kernel32.GetProcessTimes(
        handle,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        raise WindowsVerifiedProcessError(
            "GetProcessTimes failed: "
            f"WinError {ctypes.get_last_error()}"
        )

    session_id = wintypes.DWORD()

    if not kernel32.ProcessIdToSessionId(
        int(pid),
        ctypes.byref(session_id),
    ):
        raise WindowsVerifiedProcessError(
            "ProcessIdToSessionId failed: "
            f"WinError {ctypes.get_last_error()}"
        )

    return {
        "pid": int(pid),
        "creation_time_100ns":
            _filetime_value(creation),
        "executable": str(buffer.value),
        "session_id": int(session_id.value),
    }


def read_process_identity(
    pid: int,
    *,
    terminate_access: bool = False,
) -> tuple[dict[str, Any] | None, int | None]:
    """Return exact process identity plus an optional live handle."""

    _require_windows()

    if int(pid) <= 0:
        return None, None

    kernel32 = _kernel32()

    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    access = PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE

    if terminate_access:
        access |= PROCESS_TERMINATE

    handle = kernel32.OpenProcess(
        access,
        False,
        int(pid),
    )

    if not handle:
        error = ctypes.get_last_error()

        # The recorded process no longer exists or is no longer addressable.
        if error in {6, 87, 1168}:
            return None, None

        raise WindowsVerifiedProcessError(
            f"OpenProcess failed for PID {pid}: WinError {error}"
        )

    # A process object can remain openable for a short period after the
    # process has terminated. Test the synchronized handle before querying
    # executable/session identity. A signaled process is retired even if
    # its residual kernel process object is still addressable.
    kernel32.WaitForSingleObject.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    wait = kernel32.WaitForSingleObject(
        handle,
        0,
    )

    if wait == WAIT_OBJECT_0:
        kernel32.CloseHandle(handle)
        return None, None

    if wait != WAIT_TIMEOUT:
        kernel32.CloseHandle(handle)
        raise WindowsVerifiedProcessError(
            f"WaitForSingleObject failed for PID {pid}: "
            f"result {int(wait)}"
        )

    try:
        identity = _read_identity_from_handle(
            int(handle),
            int(pid),
        )
    except Exception:
        kernel32.CloseHandle(handle)
        raise

    if terminate_access:
        return identity, int(handle)

    kernel32.CloseHandle(handle)
    return identity, None


def identity_matches(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> bool:
    try:
        return (
            int(expected["pid"]) == int(actual["pid"])
            and int(expected["creation_time_100ns"])
                == int(actual["creation_time_100ns"])
            and int(expected["session_id"])
                == int(actual["session_id"])
            and _norm(str(expected["executable"]))
                == _norm(str(actual["executable"]))
        )
    except (KeyError, TypeError, ValueError):
        return False


def snapshot_game_processes(
    *,
    install_root: str,
    expected_session_id: int,
) -> list[dict[str, Any]]:
    _require_windows()

    if not str(install_root or "").strip():
        raise WindowsVerifiedProcessError(
            "Verified workload discovery requires install_root."
        )

    if int(expected_session_id) <= 0:
        raise WindowsVerifiedProcessError(
            "Verified workload discovery requires a non-zero session."
        )

    try:
        import psutil
    except ImportError as exc:
        raise WindowsVerifiedProcessError(
            "psutil is required for verified workload discovery."
        ) from exc

    result: list[dict[str, Any]] = []

    for proc in psutil.process_iter(["pid"]):
        try:
            pid = int(proc.info["pid"])
            identity, _ = read_process_identity(pid)

            if identity is None:
                continue

            if (
                int(identity["session_id"])
                != int(expected_session_id)
            ):
                continue

            if not path_is_within_install_root(
                str(identity["executable"]),
                install_root,
            ):
                continue

            result.append(identity)

        except (
            psutil.Error,
            OSError,
            ValueError,
            TypeError,
            WindowsVerifiedProcessError,
        ):
            continue

    result.sort(
        key=lambda value: (
            int(value["creation_time_100ns"]),
            int(value["pid"]),
        )
    )

    return result


def _identity_key(
    identity: dict[str, Any],
) -> tuple[int, int]:
    return (
        int(identity["pid"]),
        int(identity["creation_time_100ns"]),
    )


def diagnostic_process_identity(
    identity: dict[str, Any], install_root: str,
) -> dict[str, Any]:
    """Return bounded, root-relative facts without command lines."""
    try:
        executable = str(identity.get("executable") or "")
        verified = path_is_within_install_root(executable, install_root)
        parent_pid = None
        try:
            import psutil
            process = psutil.Process(int(identity["pid"]))
            created_epoch = (
                int(identity["creation_time_100ns"]) / 10_000_000
                - 11_644_473_600
            )
            if abs(process.create_time() - created_epoch) < 1.0:
                parent_pid = int(process.ppid())
        except Exception:
            pass
        return {
            "pid": int(identity["pid"]),
            "ppid": parent_pid,
            "creation_time_100ns": int(identity["creation_time_100ns"]),
            "session_id": int(identity["session_id"]),
            "executable_relative": (
                ntpath.relpath(executable, install_root)
                if verified else "outside_verified_root"
            )[:256],
            "verified_root": verified,
        }
    except Exception:
        return {"diagnostic_error": "identity_format_failed"}


def wait_for_new_game_processes(
    *,
    install_root: str,
    expected_session_id: int,
    baseline: list[dict[str, Any]],
    timeout_seconds: float = 45.0,
    settle_seconds: float = 1.0,
    attempt_id: str = "",
    runtime_id: str = "",
) -> list[dict[str, Any]]:
    """
    Correlate Steam's brokered launch with new processes beneath the
    already-verified AppID install root and managed Windows session.

    Pre-existing game processes are deliberately not adopted.
    """

    baseline_keys = {
        _identity_key(value)
        for value in baseline
    }

    deadline = time.monotonic() + max(
        5.0,
        float(timeout_seconds),
    )
    trace = LaunchTrace(
        attempt_id, runtime_id,
        started_monotonic=deadline - max(5.0, float(timeout_seconds)),
    )
    trace.emit(
        "observation_begin",
        baseline_count=len(baseline),
        baseline=[
            diagnostic_process_identity(value, install_root)
            for value in baseline[:16]
        ],
    )

    found: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    while time.monotonic() < deadline:
        current = snapshot_game_processes(
            install_root=install_root,
            expected_session_id=expected_session_id,
        )

        found = [
            value
            for value in current
            if _identity_key(value)
            not in baseline_keys
        ]

        for value in found:
            key = _identity_key(value)
            if key not in seen:
                trace.emit(
                    "first_candidate" if not seen
                    else "additional_or_replacement_candidate",
                    process=diagnostic_process_identity(value, install_root),
                    prior_pids=sorted(pid for pid, _ in seen)[:16],
                )
                seen.add(key)

        if found:
            # Give the launcher a bounded settling interval so closely
            # related game executables created immediately after the
            # first one are recorded into the same ownership descriptor.
            settle_deadline = min(
                deadline,
                time.monotonic()
                + max(0.0, float(settle_seconds)),
            )

            while time.monotonic() < settle_deadline:
                time.sleep(0.1)

                current = snapshot_game_processes(
                    install_root=install_root,
                    expected_session_id=expected_session_id,
                )

                found = [
                    value
                    for value in current
                    if _identity_key(value)
                    not in baseline_keys
                ]
                for value in found:
                    key = _identity_key(value)
                    if key not in seen:
                        trace.emit(
                            "additional_or_replacement_candidate",
                            process=diagnostic_process_identity(value, install_root),
                            prior_pids=sorted(pid for pid, _ in seen)[:16],
                        )
                        seen.add(key)

            break

        time.sleep(0.20)

    if not found:
        trace.emit("observation_timeout", observed_count=len(seen))
        raise WindowsVerifiedProcessError(
            "Steam launch request did not produce a new verified "
            "game process beneath the installed game root."
        )

    trace.emit(
        "observation_settled",
        process_count=len(found),
        processes=[
            diagnostic_process_identity(value, install_root)
            for value in found[:16]
        ],
    )
    return found


def make_launch_attempt_authority(
    *,
    runtime_id: str,
    install_root: str,
    expected_session_id: int,
    launcher_type: str,
    launcher_game_id: str,
    baseline: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Durable authority for one Khan-controlled brokered launch attempt.

    This is not runtime ownership.  It only permits later correlation
    with process identities that were absent from the persisted baseline.
    """
    if not str(runtime_id or "").strip():
        raise WindowsVerifiedProcessError(
            "Launch attempt requires runtime_id."
        )

    if not str(install_root or "").strip():
        raise WindowsVerifiedProcessError(
            "Launch attempt requires install_root."
        )

    if int(expected_session_id) <= 0:
        raise WindowsVerifiedProcessError(
            "Launch attempt requires a managed Windows session."
        )

    # The attempt identity is intentionally generated at the same
    # boundary as the exact pre-launch baseline.  It therefore identifies
    # one Khan-controlled Steam request rather than merely one runtime.
    #
    # Wall-clock timestamps are durable across agent/process restarts;
    # monotonic clocks are deliberately unsuitable for persisted state.
    from time import time
    from uuid import uuid4

    created_at_epoch = float(time())
    recovery_window_seconds = 180.0

    return {
        "schema_version": 2,
        "authority_type": "steam_verified_process_launch_attempt",
        "attempt_id": str(uuid4()),
        "runtime_id": str(runtime_id),
        "install_root": str(install_root),
        "interactive_session_id": int(expected_session_id),
        "launcher_type": str(launcher_type),
        "launcher_game_id": str(launcher_game_id),
        "created_at_epoch": created_at_epoch,
        "recovery_deadline_epoch": (
            created_at_epoch + recovery_window_seconds
        ),
        "recovery_window_seconds": recovery_window_seconds,
        "baseline": [
            dict(value)
            for value in baseline
        ],
    }


def discover_launch_attempt_processes(
    authority: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Discover only processes that are new relative to an exact persisted
    launch-attempt baseline.  Arbitrary pre-existing workloads remain
    non-adoptable.
    """
    if str(authority.get("authority_type") or "") != (
        "steam_verified_process_launch_attempt"
    ):
        raise WindowsVerifiedProcessError(
            "Unsupported launch-attempt authority."
        )

    install_root = str(
        authority.get("install_root") or ""
    ).strip()

    try:
        expected_session_id = int(
            authority.get("interactive_session_id") or 0
        )
    except (TypeError, ValueError):
        expected_session_id = 0

    baseline = authority.get("baseline")
    attempt_id = str(
        authority.get("attempt_id") or ""
    ).strip()

    try:
        schema_version = int(
            authority.get("schema_version") or 0
        )
        created_at_epoch = float(
            authority.get("created_at_epoch")
        )
        recovery_deadline_epoch = float(
            authority.get("recovery_deadline_epoch")
        )
    except (TypeError, ValueError):
        schema_version = 0
        created_at_epoch = 0.0
        recovery_deadline_epoch = 0.0

    if (
        schema_version != 2
        or not attempt_id
        or not install_root
        or expected_session_id <= 0
        or not isinstance(baseline, list)
        or created_at_epoch <= 0.0
        or recovery_deadline_epoch <= created_at_epoch
    ):
        raise WindowsVerifiedProcessError(
            "Launch-attempt authority is incomplete."
        )

    baseline_keys = {
        _identity_key(value)
        for value in baseline
        if isinstance(value, dict)
    }

    current = snapshot_game_processes(
        install_root=install_root,
        expected_session_id=expected_session_id,
    )

    return [
        value
        for value in current
        if _identity_key(value) not in baseline_keys
    ]



def make_verified_process_ownership(
    *,
    runtime_id: str,
    install_root: str,
    expected_session_id: int,
    launcher_type: str,
    launcher_game_id: str,
    processes: list[dict[str, Any]],
    launch_request_ownership:
        dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not processes:
        raise WindowsVerifiedProcessError(
            "Verified process ownership requires at least one process."
        )

    for identity in processes:
        if int(identity.get("session_id") or 0) != int(
            expected_session_id
        ):
            raise WindowsVerifiedProcessError(
                "Verified process belongs to the wrong Windows session."
            )

        if not path_is_within_install_root(
            str(identity.get("executable") or ""),
            install_root,
        ):
            raise WindowsVerifiedProcessError(
                "Verified process executable escaped the installed "
                "game root."
            )

    value: dict[str, Any] = {
        "schema_version": 2,
        "ownership_type": "windows_verified_process",
        "runtime_id": str(runtime_id),
        "boundary_established": True,
        "interactive_session_id":
            int(expected_session_id),
        "install_root": str(install_root),
        "launcher_type": str(launcher_type),
        "launcher_game_id": str(launcher_game_id),
        "processes": [
            dict(identity)
            for identity in processes
        ],
    }

    if launch_request_ownership is not None:
        value["launch_request_ownership"] = dict(
            launch_request_ownership
        )

    return value


def inspect_verified_process_ownership(
    ownership: dict[str, Any],
) -> dict[str, Any]:
    _require_windows()

    install_root = str(
        ownership.get("install_root") or ""
    ).strip()

    try:
        expected_session_id = int(
            ownership.get("interactive_session_id") or 0
        )
    except (TypeError, ValueError):
        expected_session_id = 0

    recorded = ownership.get("processes")

    if (
        not install_root
        or expected_session_id <= 0
        or not isinstance(recorded, list)
        or not recorded
    ):
        return {
            "ownership_type": "windows_verified_process",
            "ownership_boundary_verified": False,
            "owned_process_count": 0,
            "owned_processes": [],
            "clean": False,
            "error": "verified_process_descriptor_invalid",
        }

    live: list[int] = []
    retired: list[int] = []

    for expected in recorded:
        if not isinstance(expected, dict):
            return {
                "ownership_type": "windows_verified_process",
                "ownership_boundary_verified": False,
                "owned_process_count": len(live),
                "owned_processes": live,
                "clean": False,
                "error": "verified_process_identity_invalid",
            }

        try:
            pid = int(expected["pid"])
            expected_creation = int(
                expected["creation_time_100ns"]
            )
        except (KeyError, TypeError, ValueError):
            return {
                "ownership_type": "windows_verified_process",
                "ownership_boundary_verified": False,
                "owned_process_count": len(live),
                "owned_processes": live,
                "clean": False,
                "error": "verified_process_identity_invalid",
            }

        actual, _ = read_process_identity(pid)

        if actual is None:
            retired.append(pid)
            continue

        # Different creation time proves that the original PID identity
        # has retired and Windows has reused the numeric PID.
        if int(actual["creation_time_100ns"]) != expected_creation:
            retired.append(pid)
            continue

        # Same process lifetime but changed executable/session is not a
        # safe retirement proof. Fail closed.
        if not identity_matches(expected, actual):
            return {
                "ownership_type": "windows_verified_process",
                "ownership_boundary_verified": False,
                "owned_process_count": len(live),
                "owned_processes": live,
                "clean": False,
                "error": "verified_process_identity_mismatch",
            }

        if (
            int(actual["session_id"])
            != expected_session_id
            or not path_is_within_install_root(
                str(actual["executable"]),
                install_root,
            )
        ):
            return {
                "ownership_type": "windows_verified_process",
                "ownership_boundary_verified": False,
                "owned_process_count": len(live),
                "owned_processes": live,
                "clean": False,
                "error": "verified_process_boundary_mismatch",
            }

        live.append(pid)

    return {
        "ownership_type": "windows_verified_process",
        "ownership_boundary_verified": True,
        "owned_process_count": len(live),
        "owned_processes": live,
        "retired_processes": retired,
        "clean": not live,
    }


def terminate_verified_process_ownership(
    ownership: dict[str, Any],
    *,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """
    Terminate only exact durable identities.

    A reused PID is never terminated. A same-lifetime identity whose
    executable/session changed fails closed.
    """

    _require_windows()

    pre = inspect_verified_process_ownership(
        ownership
    )

    if not bool(
        pre.get("ownership_boundary_verified")
    ):
        raise WindowsVerifiedProcessError(
            "Verified process ownership cannot be safely terminated: "
            f"{pre.get('error') or 'unverified boundary'}"
        )

    before = list(pre.get("owned_processes") or [])

    kernel32 = _kernel32()

    kernel32.TerminateProcess.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
    ]
    kernel32.TerminateProcess.restype = wintypes.BOOL

    kernel32.WaitForSingleObject.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    recorded = [
        value
        for value in ownership.get("processes", [])
        if isinstance(value, dict)
    ]

    for expected in recorded:
        pid = int(expected["pid"])

        actual, handle = read_process_identity(
            pid,
            terminate_access=True,
        )

        if actual is None or handle is None:
            continue

        try:
            if (
                int(actual["creation_time_100ns"])
                != int(expected["creation_time_100ns"])
            ):
                # PID was reused: original workload identity is already gone.
                continue

            if not identity_matches(
                expected,
                actual,
            ):
                raise WindowsVerifiedProcessError(
                    "Recorded process identity changed before termination; "
                    "refusing destructive PID action."
                )

            if not kernel32.TerminateProcess(
                handle,
                1,
            ):
                raise WindowsVerifiedProcessError(
                    f"TerminateProcess failed for PID {pid}: "
                    f"WinError {ctypes.get_last_error()}"
                )

            wait = kernel32.WaitForSingleObject(
                handle,
                int(
                    max(1.0, float(timeout_seconds))
                    * 1000
                ),
            )

            if wait not in {
                WAIT_OBJECT_0,
            }:
                raise WindowsVerifiedProcessError(
                    f"Verified process PID {pid} did not terminate "
                    "within the bounded timeout."
                )

        finally:
            kernel32.CloseHandle(handle)

    post = inspect_verified_process_ownership(
        ownership
    )

    if not bool(
        post.get("ownership_boundary_verified")
    ):
        raise WindowsVerifiedProcessError(
            "Verified process ownership became unverified after "
            "termination."
        )

    remaining = list(
        post.get("owned_processes") or []
    )

    return {
        "ownership_type": "windows_verified_process",
        "owned_processes_before": before,
        "owned_processes_remaining": remaining,
        "owned_process_count_before": len(before),
        "owned_process_count_remaining": len(remaining),
        "termination_verified": not remaining,
        "ownership_boundary_verified": True,
        "clean": not remaining,
    }


def classify_launch_attempt_recovery(
    authority: dict[str, Any],
    *,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """
    Classify one durable brokered launch attempt without claiming that
    expiry itself proves cleanliness.

    A candidate may be adopted only when it is new relative to the exact
    persisted baseline and still satisfies the persisted root/session
    authority.  After the recovery deadline, a zero-candidate observation
    is reported separately as expired_no_candidate; callers decide whether
    an additional sanitation/reconciliation proof is required.
    """
    from time import time

    if not isinstance(authority, dict):
        raise WindowsVerifiedProcessError(
            "Launch-attempt authority is invalid."
        )

    # discover_launch_attempt_processes performs the complete schema,
    # baseline, install-root and managed-session validation.
    processes = discover_launch_attempt_processes(
        authority
    )

    deadline = float(
        authority.get("recovery_deadline_epoch")
    )
    current = (
        float(time())
        if now_epoch is None
        else float(now_epoch)
    )

    if processes:
        return {
            "state": "candidate_discovered",
            "expired": current > deadline,
            "attempt_id":
                str(authority["attempt_id"]),
            "processes": [
                dict(value)
                for value in processes
            ],
        }

    if current > deadline:
        return {
            "state": "expired_no_candidate",
            "expired": True,
            "attempt_id":
                str(authority["attempt_id"]),
            "processes": [],
        }

    return {
        "state": "pending",
        "expired": False,
        "attempt_id":
            str(authority["attempt_id"]),
        "processes": [],
    }


def ownership_from_launch_attempt(
    authority: dict[str, Any],
    processes: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Convert only a validated launch-attempt candidate set into canonical
    schema-v2 verified-process ownership.
    """
    if not processes:
        raise WindowsVerifiedProcessError(
            "Launch-attempt recovery requires a verified process."
        )

    return make_verified_process_ownership(
        runtime_id=str(authority["runtime_id"]),
        install_root=str(authority["install_root"]),
        expected_session_id=int(
            authority["interactive_session_id"]
        ),
        launcher_type=str(authority["launcher_type"]),
        launcher_game_id=str(
            authority["launcher_game_id"]
        ),
        processes=[
            dict(value)
            for value in processes
        ],
        launch_request_ownership={
            "authority_type":
                str(authority["authority_type"]),
            "attempt_id":
                str(authority["attempt_id"]),
            "created_at_epoch":
                float(authority["created_at_epoch"]),
            "recovery_deadline_epoch":
                float(
                    authority[
                        "recovery_deadline_epoch"
                    ]
                ),
        },
    )
