from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class WindowsSessionBrokerError(RuntimeError):
    pass


def _default_state_path() -> Path:
    program_data = Path(
        os.environ.get("ProgramData", r"C:\ProgramData")
    )
    return (
        program_data
        / "KhanCloud"
        / "Agent"
        / "session-broker.json"
    )


@dataclass(frozen=True)
class InteractiveSession:
    session_id: int
    available: bool
    source: str
    managed: bool = False
    username: str = ""
    broker_mode: str = "existing"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_broker_state(
    path: Path | None = None,
) -> dict[str, Any]:
    state_path = Path(path or _default_state_path())

    if not state_path.is_file():
        return {}

    try:
        value = json.loads(
            state_path.read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError, TypeError):
        return {}

    return value if isinstance(value, dict) else {}


def _normalized_account_name(value: str) -> str:
    text = str(value or "").strip().replace("/", "\\")
    return text.rsplit("\\", 1)[-1].casefold()


def _session_username(
    win32ts: Any,
    session_id: int,
) -> str:
    try:
        user = str(
            win32ts.WTSQuerySessionInformation(
                None,
                session_id,
                win32ts.WTSUserName,
            )
            or ""
        ).strip()

        domain = str(
            win32ts.WTSQuerySessionInformation(
                None,
                session_id,
                win32ts.WTSDomainName,
            )
            or ""
        ).strip()
    except Exception:
        return ""

    if not user:
        return ""

    return f"{domain}\\{user}" if domain else user


def discover_interactive_session(
    *,
    state_path: Path | None = None,
) -> InteractiveSession:
    if platform.system() != "Windows":
        return InteractiveSession(
            session_id=0,
            available=False,
            source="unsupported_platform",
        )

    try:
        import win32ts
    except ImportError as exc:
        raise WindowsSessionBrokerError(
            "pywin32 win32ts is required for Windows session discovery."
        ) from exc

    session_id = int(
        win32ts.WTSGetActiveConsoleSessionId()
    )

    if session_id in (-1, 0xFFFFFFFF):
        return InteractiveSession(
            session_id=0,
            available=False,
            source="no_active_console",
        )

    if session_id <= 0:
        return InteractiveSession(
            session_id=session_id,
            available=False,
            source="non_interactive_session",
        )

    username = _session_username(
        win32ts,
        session_id,
    )

    state = load_broker_state(state_path)

    expected_user = str(
        state.get("username") or ""
    ).strip()

    broker_mode = str(
        state.get("mode") or "existing"
    ).strip() or "existing"

    state_managed = bool(
        state.get("managed", False)
    )

    managed = bool(
        state_managed
        and expected_user
        and username
        and _normalized_account_name(username)
        == _normalized_account_name(expected_user)
    )

    return InteractiveSession(
        session_id=session_id,
        available=True,
        source=(
            "managed_console"
            if managed
            else "active_console"
        ),
        managed=managed,
        username=username,
        broker_mode=broker_mode,
    )


def require_interactive_session(
    expected_session_id: int | None = None,
    *,
    require_managed: bool = False,
    state_path: Path | None = None,
) -> InteractiveSession:
    if state_path is None:
        session = discover_interactive_session()
    else:
        session = discover_interactive_session(
            state_path=state_path,
        )

    if not session.available:
        raise WindowsSessionBrokerError(
            "No usable Windows interactive session is available."
        )

    if (
        expected_session_id is not None
        and session.session_id
        != int(expected_session_id)
    ):
        raise WindowsSessionBrokerError(
            "Windows interactive session changed before launch: "
            f"expected={expected_session_id}, "
            f"actual={session.session_id}."
        )

    if require_managed and not session.managed:
        raise WindowsSessionBrokerError(
            "Windows interactive session is not broker-managed."
        )

    return session
