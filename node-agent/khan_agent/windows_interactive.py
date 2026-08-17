from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Sequence


class InteractiveSessionError(RuntimeError):
    """A command could not be dispatched into an interactive user session."""


@dataclass(frozen=True)
class InteractiveLaunchResult:
    pid: int
    session_id: int
    execution_context: str = "interactive_user"


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
        import win32process
        import win32profile
        import win32security
        import win32ts
    except ImportError as exc:
        raise InteractiveSessionError(
            "Required pywin32 interactive-session support is unavailable."
        ) from exc

    session_id = active_console_session_id()

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

        executable = argv[0]

        # list2cmdline applies Windows CreateProcess quoting rules.
        # Launcher metadata is passed without command-shell interpretation.
        command_line = subprocess.list2cmdline(argv)

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

        process_handle.Close()
        thread_handle.Close()

        return InteractiveLaunchResult(
            pid=int(pid),
            session_id=session_id,
        )

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
