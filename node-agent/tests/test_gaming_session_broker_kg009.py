import pytest

from khan_agent import gaming_runtime


def test_windows_runtime_accepts_real_interactive_session(
    monkeypatch,
):
    monkeypatch.setattr(
        gaming_runtime.platform,
        "system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        gaming_runtime,
        "active_console_session_id",
        lambda: 2,
    )

    value = (
        gaming_runtime._interactive_session_context()
    )

    assert value == {
        "required": True,
        "validated": True,
        "session_id": 2,
        "execution_context": "interactive_user",
    }


def test_windows_runtime_rejects_session_zero(
    monkeypatch,
):
    monkeypatch.setattr(
        gaming_runtime.platform,
        "system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        gaming_runtime,
        "active_console_session_id",
        lambda: 0,
    )

    with pytest.raises(
        gaming_runtime.GamingRuntimeError,
        match="session 0 is not permitted",
    ):
        gaming_runtime._interactive_session_context()


def test_windows_runtime_fails_closed_when_session_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        gaming_runtime.platform,
        "system",
        lambda: "Windows",
    )

    def missing():
        raise gaming_runtime.InteractiveSessionError(
            "No active console session."
        )

    monkeypatch.setattr(
        gaming_runtime,
        "active_console_session_id",
        missing,
    )

    with pytest.raises(
        gaming_runtime.GamingRuntimeError,
        match="interactive session is unavailable",
    ):
        gaming_runtime._interactive_session_context()


def test_non_windows_unit_environment_does_not_fake_session(
    monkeypatch,
):
    monkeypatch.setattr(
        gaming_runtime.platform,
        "system",
        lambda: "Linux",
    )

    value = (
        gaming_runtime._interactive_session_context()
    )

    assert value["required"] is True
    assert value["validated"] is False
    assert (
        value["reason"]
        == "non_windows_test_environment"
    )


def test_runtime_orders_session_gate_before_vdd_and_game():
    from pathlib import Path

    source = Path(
        gaming_runtime.__file__
    ).read_text()

    create_start = source.index(
        "def create_session("
    )

    session_gate = source.index(
        "_interactive_session_context()",
        create_start,
    )

    display_policy = source.index(
        "_apply_session_display_policy(",
        session_gate,
    )

    game_prepare = source.index(
        "prepare_game_launch(payload)",
        display_policy,
    )

    assert (
        session_gate
        < display_policy
        < game_prepare
    )


def test_existing_interactive_launcher_boundary_is_preserved():
    from khan_agent import gaming_backends
    from pathlib import Path

    source = Path(
        gaming_backends.__file__
    ).read_text()

    assert "launch_in_active_session(command)" in source
