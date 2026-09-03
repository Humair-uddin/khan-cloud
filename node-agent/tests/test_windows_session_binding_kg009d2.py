from pathlib import Path

from khan_agent import (
    gaming_backends,
    gaming_launchers,
    gaming_runtime,
    windows_interactive,
)


def source(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


def test_interactive_launcher_has_expected_session_contract():
    text = source(windows_interactive)

    assert "expected_session_id: int | None = None" in text
    assert "require_interactive_session(" in text
    assert "expected_session_id=expected_session_id" in text


def test_prepared_launch_carries_bound_session():
    text = source(gaming_launchers)

    assert "expected_session_id: int | None = None" in text
    assert (
        "expected_session_id=prepared.expected_session_id"
        in text
    )


def test_steam_backend_forwards_bound_session():
    text = source(gaming_backends)

    assert "expected_session_id: int | None = None" in text
    assert text.count(
        "expected_session_id=expected_session_id"
    ) >= 2
    assert "ownership_name=windows_job_name(" in text


def test_runtime_uses_authoritative_broker():
    text = source(gaming_runtime)

    assert "require_interactive_session()" in text
    assert "active_console_session_id" not in text


def test_runtime_binds_both_preparation_paths():
    text = source(gaming_runtime)

    assert text.count(
        'interactive_session.get("session_id")'
    ) == 2


def test_runtime_rejects_session_zero(monkeypatch):
    monkeypatch.setattr(
        gaming_runtime.platform,
        "system",
        lambda: "Windows",
    )

    class Session:
        session_id = 0

    monkeypatch.setattr(
        gaming_runtime,
        "require_interactive_session",
        lambda: Session(),
    )

    try:
        gaming_runtime._interactive_session_context()
    except gaming_runtime.GamingRuntimeError as exc:
        assert "session 0 is not permitted" in str(exc)
    else:
        raise AssertionError("session 0 must fail closed")


def test_runtime_accepts_nonzero_broker_session(monkeypatch):
    monkeypatch.setattr(
        gaming_runtime.platform,
        "system",
        lambda: "Windows",
    )

    class Session:
        session_id = 4

    monkeypatch.setattr(
        gaming_runtime,
        "require_interactive_session",
        lambda: Session(),
    )

    assert gaming_runtime._interactive_session_context() == {
        "required": True,
        "validated": True,
        "session_id": 4,
        "execution_context": "interactive_user",
    }
