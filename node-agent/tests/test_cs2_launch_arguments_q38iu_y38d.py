from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from khan_agent.gaming_launchers import (
    PreparedGameLaunch,
    SteamLauncherAdapter,
    _game_launch_arguments,
)


def prepared(
    *,
    game_slug: str = "counter-strike-2",
    contract: dict | None = None,
    runtime_id: str = "runtime-test",
    expected_session_id: int | None = 1,
) -> PreparedGameLaunch:
    return PreparedGameLaunch(
        game_slug=game_slug,
        launcher_type="steam",
        launcher_game_id="730",
        game={
            "install_path": (
                r"C:\Program Files (x86)\Steam\steamapps\common"
                r"\Counter-Strike Global Offensive"
            )
        },
        launcher_executable=r"C:\Program Files (x86)\Steam\steam.exe",
        runtime_id=runtime_id,
        expected_session_id=expected_session_id,
        presentation_contract=contract,
    )


def verified_contract(
    width: int = 1920,
    height: int = 1080,
) -> dict:
    return {
        "verified": True,
        "width": width,
        "height": height,
        "refresh_hz": 60,
    }


def test_cs2_verified_contract_produces_exact_launch_arguments():
    value = prepared(contract=verified_contract())

    assert _game_launch_arguments(value) == (
        "-w",
        "1920",
        "-h",
        "1080",
        "-windowed",
        "-noborder",
    )


def test_cs2_uses_verified_contract_dimensions_not_hardcoded_1080p():
    value = prepared(
        contract=verified_contract(
            width=2560,
            height=1440,
        )
    )

    assert _game_launch_arguments(value) == (
        "-w",
        "2560",
        "-h",
        "1440",
        "-windowed",
        "-noborder",
    )


@pytest.mark.parametrize(
    "contract",
    [
        None,
        {},
        {"verified": False, "width": 1920, "height": 1080},
        {"verified": True, "width": 0, "height": 1080},
        {"verified": True, "width": 1920, "height": 0},
        {"verified": True, "width": -1, "height": 1080},
        {"verified": True, "width": 1920, "height": -1},
        {"verified": True, "width": True, "height": 1080},
        {"verified": True, "width": 1920, "height": False},
        {"verified": True, "width": "1920", "height": 1080},
        {"verified": True, "width": 1920, "height": "1080"},
    ],
)
def test_cs2_does_not_invent_arguments_without_valid_verified_contract(
    contract,
):
    value = prepared(contract=contract)

    assert _game_launch_arguments(value) == ()


def test_non_cs2_game_receives_no_cs2_arguments():
    value = prepared(
        game_slug="some-other-game",
        contract=verified_contract(),
    )

    assert _game_launch_arguments(value) == ()


def test_production_windows_broker_forwards_cs2_arguments(monkeypatch):
    import khan_agent.gaming_launchers as launchers

    value = prepared(contract=verified_contract())

    monkeypatch.setattr(
        launchers.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        "khan_agent.windows_verified_process.snapshot_game_processes",
        lambda **kwargs: [],
    )

    monkeypatch.setattr(
        "khan_agent.windows_verified_process.wait_for_new_game_processes",
        lambda **kwargs: [
            {
                "pid": 4242,
                "session_id": 1,
                "executable_path": (
                    value.game["install_path"] + r"\game\bin\win64\cs2.exe"
                ),
                "creation_time": "20260923200000.000000+000",
            }
        ],
    )

    monkeypatch.setattr(
        "khan_agent.windows_verified_process.make_verified_process_ownership",
        lambda **kwargs: {
            "schema_version": 2,
            "ownership_type": "windows_verified_processes",
            "processes": kwargs["processes"],
        },
    )

    request = Mock(
        return_value={
            "launcher_type": "steam",
            "launcher_game_id": "730",
            "command_mode": "steam_applaunch",
            "launcher_pid": 1111,
            "session_id": 1,
            "execution_context": "interactive_session",
        }
    )

    monkeypatch.setattr(
        launchers,
        "launch_steam_app",
        request,
    )

    result = SteamLauncherAdapter().launch(
        value,
        launch_attempt=None,
    )

    request.assert_called_once_with(
        Path(value.launcher_executable),
        "730",
        expected_session_id=1,
        launch_arguments=(
            "-w",
            "1920",
            "-h",
            "1080",
            "-windowed",
            "-noborder",
        ),
    )

    assert result["launcher_pid"] == 4242
    assert result["launch_request_pid"] == 1111
    assert result["ownership_mode"] == "steam_brokered_verified_process"


def test_runtime_owned_fallback_forwards_cs2_arguments(monkeypatch):
    import khan_agent.gaming_launchers as launchers

    value = prepared(contract=verified_contract())

    monkeypatch.setattr(
        launchers.platform,
        "system",
        lambda: "Linux",
    )

    request = Mock(
        return_value={
            "launcher_type": "steam",
            "launcher_game_id": "730",
            "launcher_pid": 1234,
        }
    )

    monkeypatch.setattr(
        launchers,
        "launch_steam_app",
        request,
    )

    SteamLauncherAdapter().launch(value)

    request.assert_called_once_with(
        Path(value.launcher_executable),
        "730",
        runtime_id="runtime-test",
        expected_session_id=1,
        launch_arguments=(
            "-w",
            "1920",
            "-h",
            "1080",
            "-windowed",
            "-noborder",
        ),
    )


def test_legacy_path_remains_argument_free(monkeypatch):
    import khan_agent.gaming_launchers as launchers

    value = prepared(
        contract=verified_contract(),
        runtime_id="",
        expected_session_id=None,
    )

    monkeypatch.setattr(
        launchers.platform,
        "system",
        lambda: "Linux",
    )

    request = Mock(
        return_value={
            "launcher_type": "steam",
            "launcher_game_id": "730",
            "launcher_pid": 1234,
        }
    )

    monkeypatch.setattr(
        launchers,
        "launch_steam_app",
        request,
    )

    SteamLauncherAdapter().launch(value)

    request.assert_called_once_with(
        Path(value.launcher_executable),
        "730",
    )
