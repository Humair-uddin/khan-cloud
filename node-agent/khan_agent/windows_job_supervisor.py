from __future__ import annotations

import ctypes
import platform
import sys
import time
from ctypes import wintypes

from khan_agent.runtime_ownership import (
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    _query_windows_job_pids_handle,
)


class LARGE_INTEGER(ctypes.Structure):
    _fields_ = [
        ("QuadPart", ctypes.c_longlong),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", LARGE_INTEGER),
        ("PerJobUserTimeLimit", LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        (
            "BasicLimitInformation",
            JOBOBJECT_BASIC_LIMIT_INFORMATION,
        ),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def main() -> int:
    if platform.system() != "Windows":
        print("ERROR:not_windows", flush=True)
        return 2

    if len(sys.argv) != 2:
        print("ERROR:job_name_required", flush=True)
        return 2

    job_name = sys.argv[1]

    kernel32 = ctypes.WinDLL(
        "kernel32",
        use_last_error=True,
    )

    kernel32.CreateJobObjectW.argtypes = [
        wintypes.LPVOID,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE

    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL

    kernel32.CloseHandle.argtypes = [
        wintypes.HANDLE,
    ]

    handle = kernel32.CreateJobObjectW(
        None,
        job_name,
    )

    if not handle:
        print(
            f"ERROR:create:{ctypes.get_last_error()}",
            flush=True,
        )
        return 3

    limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    limits.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )

    ok = kernel32.SetInformationJobObject(
        handle,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    )

    if not ok:
        error = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        print(
            f"ERROR:set_limits:{error}",
            flush=True,
        )
        return 4

    print("READY", flush=True)

    saw_process = False
    idle_deadline = time.monotonic() + 30.0

    try:
        while True:
            pids = _query_windows_job_pids_handle(
                int(handle)
            )

            if pids:
                saw_process = True

            if saw_process and not pids:
                return 0

            if (
                not saw_process
                and time.monotonic() >= idle_deadline
            ):
                return 5

            time.sleep(0.25)
    finally:
        kernel32.CloseHandle(handle)


if __name__ == "__main__":
    raise SystemExit(main())
