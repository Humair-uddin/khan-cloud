from __future__ import annotations

import ast
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


def test_create_process_boundary_targets_interactive_desktop():
    text = _source(windows_interactive)

    startup = text.index("startup = win32process.STARTUPINFO()")
    desktop = text.index(
        r'startup.lpDesktop = r"winsta0\default"',
        startup,
    )
    create = text.index(
        "CreateProcessAsUser(",
        desktop,
    )

    assert startup < desktop < create


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




def test_runtime_binds_session_to_prepared_game_without_auto_launch():
    text = _source(gaming_runtime)

    create_start = text.index(
        "def create_session("
    )
    restart_start = text.index(
        "def change_session_state("
    )

    create = text[create_start:restart_start]

    context = create.index(
        "interactive_session = ("
    )
    presentation = create.index(
        "_establish_presentation_contract(",
        context,
    )
    prepare = create.index(
        "prepare_game_launch(payload)",
        presentation,
    )
    prepared = create.index(
        "prepared_launch = replace(",
        prepare,
    )
    binding = create.index(
        'interactive_session.get("session_id")',
        prepared,
    )

    assert (
        context
        < presentation
        < prepare
        < prepared
        < binding
    )

    tree = ast.parse(create)

    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    }

    assert "prepare_game_launch" in calls
    assert "launch_prepared_game" not in calls
    assert (
        "build_prepared_launch_attempt_authority"
        not in calls
    )


def test_resource_session_uses_no_process_ownership_before_ready():
    text = _source(gaming_runtime)

    create_start = text.index(
        "def create_session("
    )
    restart_start = text.index(
        "def change_session_state("
    )

    create = text[create_start:restart_start]
    tree = ast.parse(create)

    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
    ]

    assert "no_process_ownership" in calls
    assert "_verify_stream_readiness" in calls
    assert "launch_prepared_game" not in calls
    assert (
        "build_prepared_launch_attempt_authority"
        not in calls
    )

    no_process = calls.index("no_process_ownership")
    readiness = calls.index("_verify_stream_readiness")

    assert no_process < readiness
