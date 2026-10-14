from dataclasses import replace

import pytest

from khan_agent import gaming_launchers
from khan_agent import windows_verified_process as wvp


ROOT = r"C:\Steam\steamapps\common\CS2"


def ident(pid, creation, session=7, exe=None):
    return {
        "pid": pid,
        "creation_time_100ns": creation,
        "session_id": session,
        "executable": exe or ROOT + r"\game\cs2.exe",
    }


def authority(baseline):
    return wvp.make_launch_attempt_authority(
        runtime_id="kc-gaming-test",
        install_root=ROOT,
        expected_session_id=7,
        launcher_type="steam",
        launcher_game_id="730",
        baseline=baseline,
    )


def test_q38it_preexisting_process_is_not_recovered(monkeypatch):
    old = ident(100, 1000)

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [old],
    )

    assert (
        wvp.discover_launch_attempt_processes(
            authority([old])
        )
        == []
    )


def test_q38it_late_new_process_is_recoverable(monkeypatch):
    old = ident(100, 1000)
    late = ident(200, 2000)

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [old, late],
    )

    found = wvp.discover_launch_attempt_processes(
        authority([old])
    )

    assert [value["pid"] for value in found] == [200]


def test_q38it_pid_reuse_is_new_identity(monkeypatch):
    old = ident(100, 1000)
    reused = ident(100, 2000)

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [reused],
    )

    found = wvp.discover_launch_attempt_processes(
        authority([old])
    )

    assert len(found) == 1
    assert found[0]["creation_time_100ns"] == 2000


def test_q38it_wrong_session_excluded_by_snapshot(monkeypatch):
    old = ident(100, 1000)

    # Discovery delegates session/install-root enforcement to the same
    # authoritative snapshot primitive used by normal launch correlation.
    seen = {}

    def snapshot(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        snapshot,
    )

    assert (
        wvp.discover_launch_attempt_processes(
            authority([old])
        )
        == []
    )
    assert seen["expected_session_id"] == 7
    assert seen["install_root"] == ROOT


def test_q38it_incomplete_authority_fails_closed():
    with pytest.raises(
        wvp.WindowsVerifiedProcessError,
        match="incomplete",
    ):
        wvp.discover_launch_attempt_processes(
            {
                "authority_type":
                    "steam_verified_process_launch_attempt",
                "install_root": "",
                "interactive_session_id": 7,
                "baseline": [],
            }
        )


def test_q38it_builder_records_exact_baseline(monkeypatch):
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={
            "install_path": ROOT,
            "installed": True,
        },
        launcher_executable=r"C:\Steam\steam.exe",
        runtime_id="kc-gaming-test",
        expected_session_id=7,
    )

    old = ident(100, 1000)

    monkeypatch.setattr(
        gaming_launchers.platform,
        "system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [old],
    )

    value = (
        gaming_launchers
        .SteamLauncherAdapter()
        .build_launch_attempt_authority(
            prepared
        )
    )

    assert value is not None
    assert value["runtime_id"] == "kc-gaming-test"
    assert value["launcher_game_id"] == "730"
    assert value["interactive_session_id"] == 7
    assert value["baseline"] == [old]


def test_q38it_no_generic_nonwindows_adoption(monkeypatch):
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={"install_path": ROOT},
        launcher_executable="/usr/bin/steam",
        runtime_id="kc-gaming-test",
        expected_session_id=7,
    )

    monkeypatch.setattr(
        gaming_launchers.platform,
        "system",
        lambda: "Linux",
    )

    assert (
        gaming_launchers
        .SteamLauncherAdapter()
        .build_launch_attempt_authority(
            prepared
        )
        is None
    )


def test_q38it_launch_uses_persisted_baseline_without_resnapshot(
    monkeypatch,
):
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={
            "install_path": ROOT,
            "installed": True,
        },
        launcher_executable=r"C:\Steam\steam.exe",
        runtime_id="kc-gaming-test",
        expected_session_id=7,
    )

    old = ident(100, 1000)
    new = ident(200, 2000)
    launch_attempt = authority([old])

    monkeypatch.setattr(
        gaming_launchers.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: pytest.fail(
            "second baseline snapshot is forbidden"
        ),
    )

    observed = {}

    def fake_wait(**kwargs):
        observed.update(kwargs)
        return [new]

    monkeypatch.setattr(
        wvp,
        "wait_for_new_game_processes",
        fake_wait,
    )

    monkeypatch.setattr(
        gaming_launchers,
        "launch_steam_app",
        lambda *args, **kwargs: {
            "launcher_pid": 300,
            "runtime_ownership": {},
        },
    )

    result = (
        gaming_launchers
        .SteamLauncherAdapter()
        .launch(
            prepared,
            launch_attempt=launch_attempt,
        )
    )

    assert observed["baseline"] == [old]
    assert observed["timeout_seconds"] == 120.0
    assert result["launcher_pid"] == 200


def test_q38it_mismatched_launch_authority_fails_closed(
    monkeypatch,
):
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={
            "install_path": ROOT,
            "installed": True,
        },
        launcher_executable=r"C:\Steam\steam.exe",
        runtime_id="kc-gaming-test",
        expected_session_id=7,
    )

    bad = authority([])
    bad["runtime_id"] = "wrong-runtime"

    monkeypatch.setattr(
        gaming_launchers.platform,
        "system",
        lambda: "Windows",
    )

    with pytest.raises(
        gaming_launchers.GameLaunchError,
        match="does not match",
    ):
        (
            gaming_launchers
            .SteamLauncherAdapter()
            .launch(
                prepared,
                launch_attempt=bad,
            )
        )


def test_q38it_authority_type_mismatch_fails_closed(
    monkeypatch,
):
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={
            "install_path": ROOT,
            "installed": True,
        },
        launcher_executable=r"C:\Steam\steam.exe",
        runtime_id="kc-gaming-test",
        expected_session_id=7,
    )

    bad = authority([])
    bad["authority_type"] = "untrusted"

    monkeypatch.setattr(
        gaming_launchers.platform,
        "system",
        lambda: "Windows",
    )

    with pytest.raises(
        gaming_launchers.GameLaunchError,
        match="does not match",
    ):
        (
            gaming_launchers
            .SteamLauncherAdapter()
            .launch(
                prepared,
                launch_attempt=bad,
            )
        )


def test_y9_attempt_id_is_forwarded_to_observation(monkeypatch):
    from khan_agent import gaming_launchers
    from khan_agent import windows_verified_process as wvp
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="cs2", launcher_type="steam", launcher_game_id="730",
        game={"install_path": r"C:\Games\CS2"},
        launcher_executable=r"C:\Steam\steam.exe",
        runtime_id="runtime-1", expected_session_id=1,
    )
    attempt = wvp.make_launch_attempt_authority(
        runtime_id="runtime-1",
        install_root=r"C:\Games\CS2",
        expected_session_id=1,
        launcher_type="steam",
        launcher_game_id="730",
        baseline=[],
    )
    observed = {}
    monkeypatch.setattr(gaming_launchers.platform, "system", lambda: "Windows")
    monkeypatch.setattr(gaming_launchers, "launch_steam_app",
                        lambda *_args, **_kwargs: {"launcher_pid": 9})
    monkeypatch.setattr(wvp, "wait_for_new_game_processes",
                        lambda **kwargs: observed.update(kwargs) or [{
                            "pid": 10, "creation_time_100ns": 20,
                            "executable": r"C:\Games\CS2\cs2.exe",
                            "session_id": 1,
                        }])
    monkeypatch.setattr(wvp, "make_verified_process_ownership",
                        lambda **_kwargs: {"ownership_type": "verified"})
    gaming_launchers.SteamLauncherAdapter().launch(
        prepared, launch_attempt=attempt,
    )
    assert observed["attempt_id"] == attempt["attempt_id"]
    assert observed["runtime_id"] == "runtime-1"
    assert observed["timeout_seconds"] == 120.0
