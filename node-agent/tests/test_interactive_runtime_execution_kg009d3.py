from __future__ import annotations

from pathlib import Path

from khan_agent import (
    gaming_backends,
    gaming_runtime,
    windows_interactive,
)


def _source(module) -> str:
    return Path(module.__file__).read_text(
        encoding="utf-8"
    )


def test_runtime_requires_managed_console_before_vdd_and_game():
    text = _source(gaming_runtime)

    function = text.index(
        "def _interactive_session_context("
    )
    gate = text.index(
        "require_interactive_session(",
        function,
    )
    managed = text.index(
        "require_managed=True",
        gate,
    )
    vdd = text.index(
        "_apply_session_display_policy(",
        managed,
    )
    game = text.index(
        "prepare_game_launch(payload)",
        vdd,
    )

    assert function < gate < managed < vdd < game


def test_create_process_boundary_revalidates_managed_session():
    text = _source(windows_interactive)

    gate = text.index(
        "broker_session = require_interactive_session("
    )
    expected = text.index(
        "expected_session_id=expected_session_id",
        gate,
    )
    managed = text.index(
        "require_managed=True",
        expected,
    )
    token = text.index(
        "WTSQueryUserToken(session_id)",
        managed,
    )
    create = text.index(
        "CreateProcessAsUser(",
        token,
    )

    assert gate < expected < managed < token < create


def test_steam_keeps_session_binding_and_job_ownership():
    text = _source(gaming_backends)

    function = text.index(
        "def launch_steam_app("
    )
    interactive = text.index(
        "launch_in_active_session(",
        function,
    )
    ownership = text.index(
        "ownership_name=windows_job_name(",
        interactive,
    )
    bound = text.index(
        "expected_session_id=expected_session_id",
        ownership,
    )

    assert function < interactive < ownership < bound


def test_runtime_binds_broker_session_to_prepared_launch():
    text = _source(gaming_runtime)

    context = text.index(
        "interactive_session = ("
    )
    prepared = text.index(
        "prepared_launch = replace(",
        context,
    )
    binding = text.index(
        'interactive_session.get("session_id")',
        prepared,
    )
    launch = text.index(
        "launch_prepared_game(",
        binding,
    )

    assert context < prepared < binding < launch


def test_starting_state_persists_session_and_ownership():
    text = _source(gaming_runtime)

    starting = text.index(
        '"status": "starting"'
    )
    session = text.index(
        '"interactive_session": interactive_session',
        starting,
    )
    ownership = text.index(
        '"runtime_ownership":',
        session,
    )

    assert starting < session < ownership
