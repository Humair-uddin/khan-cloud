from __future__ import annotations

import ctypes
import os
from pathlib import Path
import platform
import subprocess
import shutil
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Sequence

from khan_agent.runtime_ownership import (
    JOB_OBJECT_ASSIGN_PROCESS,
    RuntimeOwnershipError,
    open_windows_job,
)
from khan_agent.windows_session_broker import (
    WindowsSessionBrokerError,
    require_interactive_session,
)


class InteractiveSessionError(RuntimeError):
    """A command could not be dispatched into an interactive user session."""


@dataclass(frozen=True)
class InteractiveLaunchResult:
    pid: int
    session_id: int
    execution_context: str = "interactive_user"
    runtime_ownership: dict[str, Any] | None = None


def _require_windows() -> None:
    if platform.system() != "Windows":
        raise InteractiveSessionError(
            "Interactive Windows session execution is available only on Windows."
        )


def active_console_session_id() -> int:
    _require_windows()

    try:
        import win32ts
    except ImportError as exc:
        raise InteractiveSessionError(
            "pywin32 win32ts support is unavailable."
        ) from exc

    session_id = int(win32ts.WTSGetActiveConsoleSessionId())

    # Windows returns 0xFFFFFFFF when no physical console session exists.
    if session_id == 0xFFFFFFFF:
        raise InteractiveSessionError(
            "No active Windows console session is available."
        )

    return session_id


def launch_in_active_session(
    command: Sequence[str],
    *,
    ownership_name: str | None = None,
    expected_session_id: int | None = None,
) -> InteractiveLaunchResult:
    """
    Launch a process in the active interactive Windows user's session.

    The KhanCloudAgent Windows service runs as LocalSystem in session 0.
    GUI launchers and games must instead execute in the logged-in desktop
    session. No user password is stored or requested: the service obtains
    the existing interactive session token from Windows.

    This function intentionally accepts a command vector rather than a
    launcher-specific object so all current and future launch adapters
    can share the same execution boundary.
    """

    _require_windows()

    argv = [str(value) for value in command]

    if not argv or not argv[0].strip():
        raise InteractiveSessionError(
            "Interactive launch command is empty."
        )

    try:
        import win32con
        import win32event
        import win32process
        import win32profile
        import win32security
        import win32ts
    except ImportError as exc:
        raise InteractiveSessionError(
            "Required pywin32 interactive-session support is unavailable."
        ) from exc

    try:
        broker_session = require_interactive_session(
            expected_session_id=expected_session_id,
            require_managed=True,
        )
    except WindowsSessionBrokerError as exc:
        raise InteractiveSessionError(str(exc)) from exc

    session_id = int(broker_session.session_id)

    try:
        user_token = win32ts.WTSQueryUserToken(session_id)
    except Exception as exc:
        raise InteractiveSessionError(
            f"Unable to obtain the active Windows session token for session {session_id}."
        ) from exc

    primary_token = None
    environment = None

    try:
        try:
            primary_token = win32security.DuplicateTokenEx(
                user_token,
                win32security.SecurityIdentification,
                win32con.MAXIMUM_ALLOWED,
                win32security.TokenPrimary,
            )
        except Exception as exc:
            raise InteractiveSessionError(
                "DuplicateTokenEx failed for Windows session "
                f"{session_id}: {type(exc).__name__}: {exc!r}"
            ) from exc

        try:
            environment = win32profile.CreateEnvironmentBlock(
                primary_token,
                False,
            )
        except Exception as exc:
            raise InteractiveSessionError(
                "CreateEnvironmentBlock failed for Windows session "
                f"{session_id}: {type(exc).__name__}: {exc!r}"
            ) from exc

        requested_executable = argv[0]

        # CreateProcessAsUser receives lpApplicationName explicitly.  A bare
        # executable name must therefore be resolved before crossing into the
        # managed user's token rather than relying on target-session PATH
        # search semantics.  Preserve explicit paths exactly as supplied.
        if os.path.dirname(requested_executable):
            executable = requested_executable
        else:
            executable = shutil.which(requested_executable)

            if not executable:
                raise InteractiveSessionError(
                    "Unable to resolve interactive executable: "
                    f"{requested_executable}"
                )

        resolved_argv = [
            executable,
            *argv[1:],
        ]

        # list2cmdline applies Windows CreateProcess quoting rules.
        # Launcher metadata is passed without command-shell interpretation.
        command_line = subprocess.list2cmdline(resolved_argv)

        startup = win32process.STARTUPINFO()
        startup.dwFlags |= win32process.STARTF_USESHOWWINDOW
        startup.wShowWindow = win32con.SW_SHOWNORMAL

        try:
            process_handle, thread_handle, pid, _thread_id = (
                win32process.CreateProcessAsUser(
                    primary_token,
                    executable,
                    command_line,
                    None,
                    None,
                    False,
                    (
                        win32con.CREATE_UNICODE_ENVIRONMENT
                        | win32con.CREATE_NEW_PROCESS_GROUP
                        | (
                            win32con.CREATE_SUSPENDED
                            if ownership_name
                            else 0
                        )
                    ),
                    environment,
                    os.path.dirname(executable) or None,
                    startup,
                )
            )
        except Exception as exc:
            raise InteractiveSessionError(
                "CreateProcessAsUser failed for Windows session "
                f"{session_id}: {type(exc).__name__}: {exc!r}"
            ) from exc

        runtime_ownership = None
        supervisor = None
        job_handle = None

        try:
            if ownership_name:
                # The Windows service may run with a working directory
                # such as System32.  The agent is deployed as source under
                # runtime_root rather than installed into site-packages, so
                # make the supervisor import context deterministic.
                runtime_root = str(
                    Path(__file__).resolve().parents[1]
                )

                supervisor = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "khan_agent.windows_job_supervisor",
                        ownership_name,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False,
                    cwd=runtime_root,
                )

                ready = (
                    supervisor.stdout.readline().strip()
                    if supervisor.stdout is not None
                    else ""
                )

                if ready != "READY":
                    detail = ""

                    if supervisor.stderr is not None:
                        detail = supervisor.stderr.read().strip()

                    raise InteractiveSessionError(
                        "Windows runtime ownership supervisor "
                        f"failed to initialize: {ready or detail or 'no response'}"
                    )

                try:
                    job_handle = open_windows_job(
                        ownership_name,
                        access=JOB_OBJECT_ASSIGN_PROCESS,
                    )
                except RuntimeOwnershipError as exc:
                    raise InteractiveSessionError(
                        f"Unable to open runtime Job Object: {exc}"
                    ) from exc

                kernel32 = ctypes.WinDLL(
                    "kernel32",
                    use_last_error=True,
                )

                kernel32.AssignProcessToJobObject.argtypes = [
                    wintypes.HANDLE,
                    wintypes.HANDLE,
                ]
                kernel32.AssignProcessToJobObject.restype = (
                    wintypes.BOOL
                )

                if not kernel32.AssignProcessToJobObject(
                    job_handle,
                    int(process_handle),
                ):
                    error = ctypes.get_last_error()
                    raise InteractiveSessionError(
                        "AssignProcessToJobObject failed "
                        f"for Windows session {session_id}: "
                        f"WinError {error}"
                    )

                win32process.ResumeThread(thread_handle)

                runtime_ownership = {
                    "schema_version": 2,
                    "ownership_type": "windows_job_object",
                    "job_name": ownership_name,
                    "root_pid": int(pid),
                    "interactive_session_id": session_id,
                    "boundary_established": True,
                    "supervisor_pid": int(supervisor.pid),
                }

            process_handle.Close()
            thread_handle.Close()

            return InteractiveLaunchResult(
                pid=int(pid),
                session_id=session_id,
                runtime_ownership=runtime_ownership,
            )

        except Exception:
            # Ownership establishment is fail-closed.  A process
            # created suspended must not escape merely because Job Object
            # initialization failed.  Terminate it and wait for Windows to
            # signal process exit before releasing the process handle.
            try:
                process_handle.TerminateProcess(1)

                try:
                    win32event.WaitForSingleObject(
                        process_handle,
                        5000,
                    )
                except Exception:
                    pass
            except Exception:
                pass

            try:
                process_handle.Close()
            except Exception:
                pass

            try:
                thread_handle.Close()
            except Exception:
                pass

            if supervisor is not None:
                try:
                    supervisor.terminate()
                except Exception:
                    pass

            raise

        finally:
            if job_handle:
                try:
                    ctypes.WinDLL(
                        "kernel32",
                        use_last_error=True,
                    ).CloseHandle(job_handle)
                except Exception:
                    pass

    except InteractiveSessionError:
        raise
    except Exception as exc:
        raise InteractiveSessionError(
            f"Unable to launch process in Windows session {session_id}."
        ) from exc
    finally:
        if environment is not None:
            try:
                win32profile.DestroyEnvironmentBlock(environment)
            except Exception:
                pass

        if primary_token is not None:
            try:
                primary_token.Close()
            except Exception:
                pass

        try:
            user_token.Close()
        except Exception:
            pass
