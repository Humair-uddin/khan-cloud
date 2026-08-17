from pathlib import Path

import pytest

from khan_agent import gaming_launchers


def _steam_inventory():
    return {
        "installed": True,
        "games": [
            {
                "launcher": "steam",
                "app_id": "730",
                "name": "Counter-Strike 2",
                "installed": True,
                "state": "installed",
                "build_id": "24701871",
                "install_path": (
                    r"C:\Steam\steamapps\common"
                    r"\Counter-Strike Global Offensive"
                ),
                "manifest_path": (
                    r"C:\Steam\steamapps"
                    r"\appmanifest_730.acf"
                ),
            }
        ],
    }


def test_generic_session_requires_no_launcher():
    assert gaming_launchers.prepare_game_launch({}) is None


def test_steam_adapter_prepares_exact_installed_app(
    monkeypatch,
):
    monkeypatch.setattr(
        gaming_launchers,
        "collect_steam_inventory",
        _steam_inventory,
    )

    monkeypatch.setattr(
        gaming_launchers,
        "locate_steam",
        lambda: Path(
            r"C:\Program Files (x86)\Steam\steam.exe"
        ),
    )

    prepared = gaming_launchers.prepare_game_launch(
        {
            "game_slug": "counter-strike-2",
            "launcher": "steam",
            "launcher_app_id": "730",
        }
    )

    assert prepared is not None
    assert prepared.game_slug == "counter-strike-2"
    assert prepared.launcher_type == "steam"
    assert prepared.launcher_game_id == "730"
    assert prepared.game["name"] == "Counter-Strike 2"


def test_future_generic_launch_field_names_are_supported(
    monkeypatch,
):
    monkeypatch.setattr(
        gaming_launchers,
        "collect_steam_inventory",
        _steam_inventory,
    )

    monkeypatch.setattr(
        gaming_launchers,
        "locate_steam",
        lambda: Path(r"C:\Steam\steam.exe"),
    )

    prepared = gaming_launchers.prepare_game_launch(
        {
            "game_slug": "counter-strike-2",
            "launcher_type": "steam",
            "launcher_game_id": "730",
        }
    )

    assert prepared is not None
    assert prepared.launcher_type == "steam"
    assert prepared.launcher_game_id == "730"


def test_absent_game_fails_closed(monkeypatch):
    monkeypatch.setattr(
        gaming_launchers,
        "collect_steam_inventory",
        lambda: {
            "installed": True,
            "games": [],
        },
    )

    monkeypatch.setattr(
        gaming_launchers,
        "locate_steam",
        lambda: Path(r"C:\Steam\steam.exe"),
    )

    with pytest.raises(
        gaming_launchers.GameLaunchError,
        match="AppID 730 is not installed",
    ):
        gaming_launchers.prepare_game_launch(
            {
                "game_slug": "counter-strike-2",
                "launcher_type": "steam",
                "launcher_game_id": "730",
            }
        )


def test_unknown_launcher_fails_closed():
    with pytest.raises(
        gaming_launchers.GameLaunchError,
        match="Unsupported gaming launcher",
    ):
        gaming_launchers.prepare_game_launch(
            {
                "game_slug": "some-game",
                "launcher_type": "unknown-store",
                "launcher_game_id": "123",
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "launcher_type": "steam",
            "launcher_game_id": "730",
        },
        {
            "game_slug": "counter-strike-2",
            "launcher_game_id": "730",
        },
        {
            "game_slug": "counter-strike-2",
            "launcher_type": "steam",
        },
    ],
)
def test_partial_launch_identity_fails_closed(payload):
    with pytest.raises(gaming_launchers.GameLaunchError):
        gaming_launchers.prepare_game_launch(payload)


def test_launch_routes_through_registered_adapter(
    monkeypatch,
):
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={"app_id": "730"},
        launcher_executable=r"C:\Steam\steam.exe",
    )

    calls = []

    monkeypatch.setattr(
        gaming_launchers,
        "launch_steam_app",
        lambda executable, app_id: (
            calls.append((str(executable), app_id))
            or {
                "launcher_type": "steam",
                "launcher_game_id": app_id,
                "launcher_pid": 4242,
            }
        ),
    )

    result = gaming_launchers.launch_prepared_game(
        prepared
    )

    assert calls == [
        (r"C:\Steam\steam.exe", "730")
    ]
    assert result["launcher_pid"] == 4242
    assert result["game_slug"] == "counter-strike-2"
