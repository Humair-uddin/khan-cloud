from pathlib import Path

from khan_agent import windows_presentation


def _source() -> str:
    return Path(
        windows_presentation.__file__
    ).read_text(encoding="utf-8")


def test_q38iu_production_command_has_no_startup_probe():
    source = _source()

    assert '"--helper"' in source
    assert '"--install-root"' in source
    assert '"--expected-session-id"' in source
    assert '"--timeout"' in source

    assert "--startup-probe" not in source
    assert "startup_probe" not in source


def test_q38iu_temporary_exit_91_is_absent():
    source = _source()

    assert "return 91" not in source
    assert "Q38AL TEMPORARY" not in source


def test_q38iu_helper_dispatches_to_real_run_helper():
    source = _source()

    main = source.index("def _main() -> int:")
    require_helper = source.index(
        "if not args.helper:",
        main,
    )
    dispatch = source.index(
        "return _run_helper(",
        require_helper,
    )

    between = source[require_helper:dispatch]

    assert "startup_probe" not in between
    assert "return 91" not in between


def test_q38iu_real_helper_exit_contract_remains():
    source = _source()

    assert "return 20" in source
    assert "return 21" in source
    assert "return 22" in source
    assert "return 23" in source
    assert "return 30" in source
    assert "return 0" in source


def test_q38iu_real_helper_keeps_vdd_and_session_filters():
    source = _source()

    assert "_resolve_vdd_monitor()" in source
    assert "_game_pids(" in source
    assert "expected_session_id=" in source
    assert "_largest_visible_window(" in source
    assert "_verify_window_presentation(" in source
    assert "MonitorFromWindow" in source
    assert "GetClientRect" in source
    assert "DwmGetWindowAttribute" in source
    assert "SetWindowPos" not in source


def test_q38iu_stream_readiness_still_fails_closed():
    source = _source()

    assert (
        "Customer-presentation verification timed out."
        in source
    )

    assert (
        "Khan VDD presentation target was not found."
        in source
    )

    assert (
        "No visible game window appeared before timeout."
        in source
    )

    assert (
        "Game window presentation evidence could not be collected."
        in source
    )

    assert (
        "Game window does not satisfy the requested "
        "Khan VDD presentation contract."
        in source
    )


def test_y9_presentation_command_carries_attempt_without_timeout_change():
    source = _source()
    assert '"--attempt-id"' in source
    assert '"--runtime-id"' in source
    assert '"--timeout"' in source
    assert "timeout: float = 75.0" in source
    assert "default=75.0" in source


def test_y9_desktop_diagnostics_are_read_only():
    source = _source()
    assert "GetProcessWindowStation" in source
    assert "GetThreadDesktop" in source
    assert "OpenInputDesktop" in source
    assert "EnumDesktopWindows" in source
    assert "SetThreadDesktop" not in source
    assert "SwitchDesktop" not in source
    assert "SetProcessWindowStation" not in source


def test_y9_window_timeout_still_uses_monotonic_deadline():
    source = _source()
    assert "deadline = time.monotonic() + max(" in source
    assert "while time.monotonic() < deadline:" in source
    assert "time.sleep(0.4)" in source
    assert "return 21" in source


def test_y9_helper_records_actual_and_expected_session_ids():
    source = _source()
    assert "ProcessIdToSessionId" in source
    assert "expected_session_id={expected_session_id}" in source
    assert "actual_session_id={actual_session}" in source
    assert "session_error={session_error!r}" in source
