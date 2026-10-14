from pathlib import Path

import pytest

from khan_agent import gaming_launchers
from khan_agent import runtime_ownership
from khan_agent import windows_verified_process as wvp


def _identity(
    pid=5000,
    creation=123456789,
    session=7,
    exe=r"C:\Steam\steamapps\common\CS2\game\cs2.exe",
):
    return {
        "pid": pid,
        "creation_time_100ns": creation,
        "session_id": session,
        "executable": exe,
    }


def _ownership(processes=None):
    return wvp.make_verified_process_ownership(
        runtime_id="kc-gaming-test",
        install_root=r"C:\Steam\steamapps\common\CS2",
        expected_session_id=7,
        launcher_type="steam",
        launcher_game_id="730",
        processes=processes or [_identity()],
        launch_request_ownership={
            "ownership_type": "windows_job_object",
            "job_name": "Global\\KhanCloudGaming_test",
            "boundary_established": True,
        },
    )


def test_q38df_install_root_boundary():
    assert wvp.path_is_within_install_root(
        r"C:\Steam\steamapps\common\CS2\game\cs2.exe",
        r"C:\Steam\steamapps\common\CS2",
    )

    assert not wvp.path_is_within_install_root(
        r"C:\Windows\System32\cmd.exe",
        r"C:\Steam\steamapps\common\CS2",
    )


def test_q38df_make_verified_process_ownership():
    value = _ownership()

    assert (
        value["ownership_type"]
        == "windows_verified_process"
    )
    assert value["interactive_session_id"] == 7
    assert value["launcher_game_id"] == "730"
    assert value["processes"][0]["pid"] == 5000
    assert (
        value["launch_request_ownership"]["ownership_type"]
        == "windows_job_object"
    )


def test_q38df_inspect_exact_live_identity(monkeypatch):
    monkeypatch.setattr(
        wvp,
        "_require_windows",
        lambda: None,
    )
    monkeypatch.setattr(
        wvp,
        "read_process_identity",
        lambda pid: (_identity(pid=pid), None),
    )

    proof = wvp.inspect_verified_process_ownership(
        _ownership()
    )

    assert proof["ownership_boundary_verified"] is True
    assert proof["owned_process_count"] == 1
    assert proof["owned_processes"] == [5000]
    assert proof["clean"] is False


def test_q38df_pid_reuse_is_retired_not_adopted(monkeypatch):
    monkeypatch.setattr(
        wvp,
        "_require_windows",
        lambda: None,
    )

    reused = _identity(
        creation=999999999,
        exe=r"C:\Windows\System32\notepad.exe",
    )

    monkeypatch.setattr(
        wvp,
        "read_process_identity",
        lambda pid: (reused, None),
    )

    proof = wvp.inspect_verified_process_ownership(
        _ownership()
    )

    assert proof["ownership_boundary_verified"] is True
    assert proof["owned_process_count"] == 0
    assert proof["clean"] is True
    assert proof["retired_processes"] == [5000]


def test_q38df_same_lifetime_wrong_path_fails_closed(
    monkeypatch,
):
    monkeypatch.setattr(
        wvp,
        "_require_windows",
        lambda: None,
    )

    wrong = _identity(
        exe=r"C:\Windows\System32\cmd.exe",
    )

    monkeypatch.setattr(
        wvp,
        "read_process_identity",
        lambda pid: (wrong, None),
    )

    proof = wvp.inspect_verified_process_ownership(
        _ownership()
    )

    assert proof["ownership_boundary_verified"] is False
    assert proof["clean"] is False
    assert (
        proof["error"]
        == "verified_process_identity_mismatch"
    )


def test_q38df_preexisting_game_not_adopted(monkeypatch):
    monkeypatch.setattr(
        wvp,
        "_require_windows",
        lambda: None,
    )

    existing = _identity()

    calls = {"n": 0}

    def snapshot(**kwargs):
        calls["n"] += 1
        return [existing]

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        snapshot,
    )

    monkeypatch.setattr(
        wvp.time,
        "sleep",
        lambda value: None,
    )

    timeline = iter([0.0, 0.1, 9.0])

    monkeypatch.setattr(
        wvp.time,
        "monotonic",
        lambda: next(timeline, 9.0),
    )

    with pytest.raises(
        wvp.WindowsVerifiedProcessError,
        match="did not produce a new verified",
    ):
        wvp.wait_for_new_game_processes(
            install_root=r"C:\Steam\steamapps\common\CS2",
            expected_session_id=7,
            baseline=[existing],
            timeout_seconds=5.0,
        )


def test_q38df_runtime_dispatch_supports_verified_process(
    monkeypatch,
):
    monkeypatch.setattr(
        wvp,
        "_require_windows",
        lambda: None,
    )
    monkeypatch.setattr(
        wvp,
        "read_process_identity",
        lambda pid: (_identity(pid=pid), None),
    )

    proof = runtime_ownership.inspect_runtime_ownership(
        _ownership()
    )

    assert proof["ownership_boundary_verified"] is True
    assert proof["owned_process_count"] == 1


def test_q38df_steam_broker_replaces_transient_job_ownership(
    monkeypatch,
):
    prepared = gaming_launchers.PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={
            "launcher": "steam",
            "app_id": "730",
            "installed": True,
            "install_path":
                r"C:\Steam\steamapps\common\CS2",
        },
        launcher_executable=r"C:\Steam\steam.exe",
        runtime_id="kc-gaming-test",
        expected_session_id=7,
    )

    monkeypatch.setattr(
        gaming_launchers.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [],
    )

    process = _identity()

    monkeypatch.setattr(
        wvp,
        "wait_for_new_game_processes",
        lambda **kwargs: [process],
    )

    monkeypatch.setattr(
        gaming_launchers,
        "launch_steam_app",
        lambda *args, **kwargs: {
            "launcher_type": "steam",
            "launcher_game_id": "730",
            "launcher_pid": 4000,
            "session_id": 7,
            "execution_context": "interactive_user",
            "runtime_ownership": {
                "schema_version": 2,
                "ownership_type":
                    "windows_job_object",
                "job_name":
                    "Global\\KhanCloudGaming_test",
                "root_pid": 4000,
                "interactive_session_id": 7,
                "boundary_established": True,
                "supervisor_pid": 4001,
            },
        },
    )

    result = (
        gaming_launchers
        .SteamLauncherAdapter()
        .launch(prepared)
    )

    assert result["launch_request_pid"] == 4000
    assert result["launcher_pid"] == 5000
    assert (
        result["runtime_ownership"]["ownership_type"]
        == "windows_verified_process"
    )
    assert (
        result["ownership_mode"]
        == "steam_brokered_verified_process"
    )


def test_q38df_reconciliation_has_retired_workload_branch():
    source = Path(
        __import__(
            "khan_agent.gaming_runtime",
            fromlist=["x"],
        ).__file__
    ).read_text()

    assert '"workload_retired"' in source
    assert (
        '"verified_runtime_has_no_live_owned_process"'
        in source
    )


def test_q38df_presentation_filters_managed_session():
    source = Path(
        __import__(
            "khan_agent.windows_presentation",
            fromlist=["x"],
        ).__file__
    ).read_text()

    assert "--expected-session-id" in source
    assert "read_process_identity" in source
