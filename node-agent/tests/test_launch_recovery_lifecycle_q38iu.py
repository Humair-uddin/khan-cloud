from __future__ import annotations

from pathlib import Path

import pytest

from khan_agent import gaming_runtime
from khan_agent import windows_verified_process as wvp


ROOT = r"C:\SteamLibrary\steamapps\common\Counter-Strike Global Offensive"


def ident(
    pid: int,
    created: int,
    *,
    session: int = 7,
    executable: str | None = None,
):
    return {
        "pid": pid,
        "creation_time_100ns": created,
        "executable": (
            executable
            or ROOT + r"\game\bin\win64\cs2.exe"
        ),
        "session_id": session,
    }


def authority(
    *,
    baseline=None,
):
    value = wvp.make_launch_attempt_authority(
        runtime_id="kc-gaming-test",
        install_root=ROOT,
        expected_session_id=7,
        launcher_type="steam",
        launcher_game_id="730",
        baseline=list(baseline or []),
    )
    return value


def test_q38iu_authority_is_unique_and_bounded():
    first = authority()
    second = authority()

    assert first["schema_version"] == 2
    assert first["attempt_id"]
    assert second["attempt_id"]
    assert first["attempt_id"] != second["attempt_id"]

    assert (
        first["recovery_deadline_epoch"]
        > first["created_at_epoch"]
    )
    assert (
        first["recovery_window_seconds"]
        == 180.0
    )


def test_q38iu_preexisting_process_remains_excluded(
    monkeypatch,
):
    old = ident(100, 1000)
    value = authority(baseline=[old])

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [old],
    )

    result = wvp.classify_launch_attempt_recovery(
        value,
        now_epoch=value["created_at_epoch"] + 1,
    )

    assert result["state"] == "pending"
    assert result["processes"] == []


def test_q38iu_new_identity_is_recoverable(
    monkeypatch,
):
    old = ident(100, 1000)
    new = ident(200, 2000)
    value = authority(baseline=[old])

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [old, new],
    )

    result = wvp.classify_launch_attempt_recovery(
        value,
        now_epoch=value["created_at_epoch"] + 1,
    )

    assert result["state"] == "candidate_discovered"
    assert result["processes"] == [new]

    ownership = wvp.ownership_from_launch_attempt(
        value,
        result["processes"],
    )

    assert (
        ownership["ownership_type"]
        == "windows_verified_process"
    )
    assert ownership["processes"] == [new]
    assert (
        ownership["launch_request_ownership"][
            "attempt_id"
        ]
        == value["attempt_id"]
    )


def test_q38iu_pid_reuse_is_new_identity(
    monkeypatch,
):
    old = ident(100, 1000)
    reused = ident(100, 2000)
    value = authority(baseline=[old])

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [reused],
    )

    result = wvp.classify_launch_attempt_recovery(
        value,
        now_epoch=value["created_at_epoch"] + 1,
    )

    assert result["state"] == "candidate_discovered"
    assert result["processes"] == [reused]


def test_q38iu_expiry_is_not_reported_clean(
    monkeypatch,
):
    value = authority()

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [],
    )

    result = wvp.classify_launch_attempt_recovery(
        value,
        now_epoch=value["recovery_deadline_epoch"] + 1,
    )

    assert result["state"] == "expired_no_candidate"
    assert "clean" not in result


def test_q38iu_candidate_after_deadline_is_not_lost(
    monkeypatch,
):
    new = ident(200, 2000)
    value = authority()

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [new],
    )

    result = wvp.classify_launch_attempt_recovery(
        value,
        now_epoch=value["recovery_deadline_epoch"] + 1,
    )

    assert result["state"] == "candidate_discovered"
    assert result["expired"] is True


def test_q38iu_incomplete_legacy_authority_fails_closed(
    monkeypatch,
):
    value = authority()
    value.pop("attempt_id")

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [],
    )

    with pytest.raises(
        wvp.WindowsVerifiedProcessError
    ):
        wvp.discover_launch_attempt_processes(value)


def test_q38iu_runtime_pending_helper_recovers_exact_identity(
    monkeypatch,
):
    value = authority()
    new = ident(300, 3000)

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: [new],
    )

    state = {
        "runtime_stage": "launch_recovery_pending",
        "launch_attempt": value,
    }

    result = (
        gaming_runtime._inspect_pending_launch_attempt(
            state
        )
    )

    assert result["state"] == "candidate_discovered"
    assert (
        result["runtime_ownership"]["processes"]
        == [new]
    )


def test_q38iu_runtime_pending_without_authority_fails_closed():
    with pytest.raises(
        gaming_runtime.GamingRuntimeError
    ):
        gaming_runtime._inspect_pending_launch_attempt(
            {
                "runtime_stage":
                    "launch_recovery_pending",
            }
        )


def test_q38iu_runtime_nonpending_does_not_discover():
    assert (
        gaming_runtime._inspect_pending_launch_attempt(
            {"runtime_stage": "stopped"}
        )
        == {"state": "not_pending"}
    )



def test_q38iu_create_does_not_create_launch_attempt():
    source = Path(
        gaming_runtime.__file__
    ).read_text(encoding="utf-8")

    create_start = source.index(
        "def create_session("
    )
    change_start = source.index(
        "def change_session_state("
    )

    create = source[create_start:change_start]

    assert "prepare_game_launch(payload)" in create

    executable_lines = [
        line
        for line in create.splitlines()
        if not line.lstrip().startswith("#")
    ]
    executable = "\n".join(executable_lines)

    assert "launch_prepared_game(" not in executable
    assert (
        "build_prepared_launch_attempt_authority("
        not in executable
    )

    # Commercial CREATE must not manufacture a pending launch
    # generation now that customer owns the PLAY action.
    assert (
        '"runtime_stage": "launch_recovery_pending"'
        not in executable
    )


def test_q38iu_restart_does_not_create_launch_attempt():
    source = Path(
        gaming_runtime.__file__
    ).read_text(encoding="utf-8")

    change_start = source.index(
        "def change_session_state("
    )
    inspect_start = source.index(
        "def _inspect_pending_launch_attempt("
    )

    restart_area = source[
        change_start:inspect_start
    ]

    assert (
        "prepare_game_launch("
        in restart_area
    )

    executable_lines = [
        line
        for line in restart_area.splitlines()
        if not line.lstrip().startswith("#")
    ]
    executable = "\n".join(executable_lines)

    assert "launch_prepared_game(" not in executable

    # Restart may still clean/reconcile old durable launch-attempt
    # state. It must not create a new launch authority merely
    # because the commercial resource session is restarted.
    assert (
        "build_prepared_launch_attempt_authority("
        not in executable
    )

def test_q38iu_reconciliation_checks_pending_before_ownership():
    source = Path(
        gaming_runtime.__file__
    ).read_text(encoding="utf-8")

    pending = source.index(
        '== "launch_recovery_pending"',
        source.index(
            "def reconcile_runtime_ownership"
        ),
    )
    ownership = source.index(
        'ownership = state.get(',
        pending,
    )

    assert pending < ownership


def test_q38iu_success_clears_attempt_metadata():
    source = Path(
        gaming_runtime.__file__
    ).read_text(encoding="utf-8")

    assert (
        'state.pop("launch_attempt", None)'
        in source
    )
    assert (
        'state.pop("launch_failure", None)'
        in source
    )
