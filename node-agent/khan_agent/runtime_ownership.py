from __future__ import annotations

import ctypes
import os
import platform
import signal
import time
from ctypes import wintypes
from typing import Any


OWNERSHIP_SCHEMA_VERSION = 2

JOB_OBJECT_ASSIGN_PROCESS = 0x0001
JOB_OBJECT_QUERY = 0x0004
JOB_OBJECT_TERMINATE = 0x0008

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

JOB_OBJECT_BASIC_PROCESS_ID_LIST = 3
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


class RuntimeOwnershipError(RuntimeError):
    pass


def windows_job_name(runtime_id: str) -> str:
    safe = "".join(
        ch
        for ch in str(runtime_id)
        if ch.isalnum() or ch in {"-", "_"}
    )

    if not safe:
        raise RuntimeOwnershipError(
            "Runtime identifier cannot form a Windows Job Object name."
        )

    return rf"Global\KhanCloudGaming_{safe}"


def planned_runtime_ownership(runtime_id: str) -> dict[str, Any]:
    if platform.system() == "Windows":
        return {
            "schema_version": OWNERSHIP_SCHEMA_VERSION,
            "ownership_type": "windows_job_object",
            "job_name": windows_job_name(runtime_id),
            "root_pid": None,
            "boundary_established": False,
        }

    return {
        "schema_version": OWNERSHIP_SCHEMA_VERSION,
        "ownership_type": "posix_process_group",
        "process_group_id": None,
        "session_id": None,
        "root_pid": None,
        "boundary_established": False,
    }


def no_process_ownership() -> dict[str, Any]:
    return {
        "schema_version": OWNERSHIP_SCHEMA_VERSION,
        "ownership_type": "none",
        "boundary_established": True,
    }


def _kernel32():
    if platform.system() != "Windows":
        raise RuntimeOwnershipError(
            "Windows Job Object operation requested on non-Windows host."
        )

    return ctypes.WinDLL(
        "kernel32",
        use_last_error=True,
    )


def _close_handle(handle: int | None) -> None:
    if not handle:
        return

    kernel32 = _kernel32()
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(handle)


def open_windows_job(
    job_name: str,
    *,
    access: int,
) -> int:
    kernel32 = _kernel32()

    kernel32.OpenJobObjectW.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.OpenJobObjectW.restype = wintypes.HANDLE

    handle = kernel32.OpenJobObjectW(
        access,
        False,
        job_name,
    )

    if not handle:
        error = ctypes.get_last_error()
        raise RuntimeOwnershipError(
            f"OpenJobObjectW failed for {job_name}: WinError {error}"
        )

    return int(handle)


def _query_windows_job_pids_handle(
    handle: int,
) -> list[int]:
    kernel32 = _kernel32()

    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL

    pointer_size = ctypes.sizeof(ctypes.c_void_p)
    capacity = 64

    for _ in range(6):
        size = 8 + (pointer_size * capacity)
        buffer = ctypes.create_string_buffer(size)
        returned = wintypes.DWORD()

        ok = kernel32.QueryInformationJobObject(
            handle,
            JOB_OBJECT_BASIC_PROCESS_ID_LIST,
            buffer,
            size,
            ctypes.byref(returned),
        )

        assigned = int.from_bytes(
            buffer.raw[0:4],
            byteorder="little",
            signed=False,
        )
        listed = int.from_bytes(
            buffer.raw[4:8],
            byteorder="little",
            signed=False,
        )

        if ok and listed <= capacity:
            result: list[int] = []

            for index in range(listed):
                offset = 8 + (index * pointer_size)
                value = int.from_bytes(
                    buffer.raw[offset:offset + pointer_size],
                    byteorder="little",
                    signed=False,
                )

                if value > 0:
                    result.append(value)

            return result

        if assigned > capacity:
            capacity = max(capacity * 2, assigned + 16)
            continue

        error = ctypes.get_last_error()
        raise RuntimeOwnershipError(
            f"QueryInformationJobObject failed: WinError {error}"
        )

    raise RuntimeOwnershipError(
        "Windows Job Object process list exceeded bounded query capacity."
    )


def query_windows_job_processes(
    job_name: str,
) -> list[int]:
    handle = open_windows_job(
        job_name,
        access=JOB_OBJECT_QUERY,
    )

    try:
        return _query_windows_job_pids_handle(handle)
    finally:
        _close_handle(handle)


def terminate_windows_job(
    job_name: str,
    *,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    handle = open_windows_job(
        job_name,
        access=(
            JOB_OBJECT_QUERY
            | JOB_OBJECT_TERMINATE
        ),
    )

    try:
        before = _query_windows_job_pids_handle(handle)

        kernel32 = _kernel32()
        kernel32.TerminateJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.UINT,
        ]
        kernel32.TerminateJobObject.restype = wintypes.BOOL

        if before:
            if not kernel32.TerminateJobObject(handle, 1):
                error = ctypes.get_last_error()
                raise RuntimeOwnershipError(
                    f"TerminateJobObject failed: WinError {error}"
                )

        deadline = time.monotonic() + timeout_seconds
        remaining = before

        while time.monotonic() < deadline:
            remaining = _query_windows_job_pids_handle(handle)

            if not remaining:
                break

            time.sleep(0.1)

        return {
            "ownership_type": "windows_job_object",
            "job_name": job_name,
            "owned_processes_before": before,
            "owned_processes_remaining": remaining,
            "owned_process_count_before": len(before),
            "owned_process_count_remaining": len(remaining),
            "termination_verified": not remaining,
            "ownership_boundary_verified": True,
        }
    finally:
        _close_handle(handle)


def _process_group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    return True


def terminate_posix_group(
    ownership: dict[str, Any],
    *,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    try:
        pgid = int(ownership.get("process_group_id") or 0)
    except (TypeError, ValueError):
        pgid = 0

    if pgid <= 0:
        raise RuntimeOwnershipError(
            "POSIX runtime ownership is missing process_group_id."
        )

    before_alive = _process_group_alive(pgid)

    if before_alive:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            before_alive = False

    deadline = time.monotonic() + min(timeout_seconds, 5.0)

    while (
        before_alive
        and time.monotonic() < deadline
        and _process_group_alive(pgid)
    ):
        time.sleep(0.1)

    if _process_group_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    deadline = time.monotonic() + max(
        0.5,
        timeout_seconds - 5.0,
    )

    while (
        time.monotonic() < deadline
        and _process_group_alive(pgid)
    ):
        time.sleep(0.1)

    remaining = _process_group_alive(pgid)

    return {
        "ownership_type": "posix_process_group",
        "process_group_id": pgid,
        "owned_processes_before": (
            ["process_group"] if before_alive else []
        ),
        "owned_processes_remaining": (
            ["process_group"] if remaining else []
        ),
        "owned_process_count_before": int(before_alive),
        "owned_process_count_remaining": int(remaining),
        "termination_verified": not remaining,
        "ownership_boundary_verified": True,
    }


def terminate_runtime_ownership(
    ownership: dict[str, Any],
) -> dict[str, Any]:
    ownership_type = str(
        ownership.get("ownership_type") or ""
    )

    if ownership_type == "none":
        return {
            "ownership_type": "none",
            "owned_processes_before": [],
            "owned_processes_remaining": [],
            "owned_process_count_before": 0,
            "owned_process_count_remaining": 0,
            "termination_verified": True,
            "ownership_boundary_verified": True,
        }

    if ownership_type == "windows_job_object":
        job_name = str(
            ownership.get("job_name") or ""
        )

        if not job_name:
            raise RuntimeOwnershipError(
                "Windows runtime ownership is missing job_name."
            )

        return terminate_windows_job(job_name)

    if ownership_type == "posix_process_group":
        return terminate_posix_group(ownership)

    raise RuntimeOwnershipError(
        f"Unsupported runtime ownership type: "
        f"{ownership_type or '<missing>'}"
    )


def inspect_runtime_ownership(
    ownership: dict[str, Any],
) -> dict[str, Any]:
    ownership_type = str(
        ownership.get("ownership_type") or ""
    )

    if ownership_type == "none":
        return {
            "ownership_type": "none",
            "ownership_boundary_verified": True,
            "owned_process_count": 0,
            "owned_processes": [],
            "clean": True,
        }

    if ownership_type == "windows_job_object":
        job_name = str(
            ownership.get("job_name") or ""
        )

        try:
            pids = query_windows_job_processes(job_name)
        except RuntimeOwnershipError as exc:
            return {
                "ownership_type": ownership_type,
                "job_name": job_name,
                "ownership_boundary_verified": False,
                "clean": False,
                "error": str(exc),
            }

        return {
            "ownership_type": ownership_type,
            "job_name": job_name,
            "ownership_boundary_verified": True,
            "owned_process_count": len(pids),
            "owned_processes": pids,
            "clean": not pids,
        }

    if ownership_type == "posix_process_group":
        try:
            pgid = int(
                ownership.get("process_group_id") or 0
            )
        except (TypeError, ValueError):
            pgid = 0

        if pgid <= 0:
            return {
                "ownership_type": ownership_type,
                "ownership_boundary_verified": False,
                "clean": False,
                "error": "process_group_id_missing",
            }

        alive = _process_group_alive(pgid)

        return {
            "ownership_type": ownership_type,
            "process_group_id": pgid,
            "ownership_boundary_verified": True,
            "owned_process_count": int(alive),
            "owned_processes": (
                ["process_group"] if alive else []
            ),
            "clean": not alive,
        }

    return {
        "ownership_type": ownership_type,
        "ownership_boundary_verified": False,
        "clean": False,
        "error": "unsupported_ownership_type",
    }
