from __future__ import annotations

import pytest

from khan_agent import windows_workload_observer as observer
from khan_agent import windows_verified_process as wvp


ROOT = (
    r"C:\SteamLibrary\steamapps\common"
    r"\Counter-Strike Global Offensive"
)


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


def authority(*, baseline=None):
    return observer.make_workload_observation_authority(
        runtime_id="kc-gaming-test",
        install_root=ROOT,
        expected_session_id=7,
        launcher_type="steam",
        launcher_game_id="730",
        baseline=list(baseline or []),
    )


def test_y44e_authority_is_customer_observation_not_launch():
    value = authority()

    assert value["schema_version"] == 1
    assert (
        value["authority_type"]
        == "customer_game_workload_observation"
    )
    assert value["runtime_id"] == "kc-gaming-test"
    assert value["interactive_session_id"] == 7
    assert value["launcher_type"] == "steam"
    assert value["launcher_game_id"] == "730"
    assert value["baseline"] == []

    assert "attempt_id" not in value
    assert "recovery_deadline_epoch" not in value
    assert "launch_request_ownership" not in value


def test_y44e_preexisting_process_is_not_adoptable(
    monkeypatch,
):
    old = ident(100, 1000)
    value = authority(baseline=[old])

    monkeypatch.setattr(
        observer,
        "snapshot_game_processes",
        lambda **kwargs: [old],
    )

    assert (
        observer.discover_customer_workload_processes(
            value
        )
        == []
    )


def test_y44e_new_customer_process_is_discovered(
    monkeypatch,
):
    old = ident(100, 1000)
    new = ident(200, 2000)

    value = authority(baseline=[old])

    monkeypatch.setattr(
        observer,
        "snapshot_game_processes",
        lambda **kwargs: [old, new],
    )

    result = (
        observer.discover_customer_workload_processes(
            value
        )
    )

    assert result == [new]


def test_y44e_pid_reuse_is_new_process_generation(
    monkeypatch,
):
    old = ident(100, 1000)
    reused = ident(100, 2000)

    value = authority(baseline=[old])

    monkeypatch.setattr(
        observer,
        "snapshot_game_processes",
        lambda **kwargs: [reused],
    )

    result = (
        observer.discover_customer_workload_processes(
            value
        )
    )

    assert result == [reused]


def test_y44e_adoption_builds_canonical_d1_ownership():
    new = ident(200, 2000)
    value = authority()

    ownership = observer.adopt_customer_workload(
        value,
        [new],
    )

    assert (
        ownership["ownership_type"]
        == "windows_verified_process"
    )
    assert ownership["boundary_established"] is True
    assert ownership["runtime_id"] == "kc-gaming-test"
    assert ownership["interactive_session_id"] == 7
    assert ownership["install_root"] == ROOT
    assert ownership["launcher_type"] == "steam"
    assert ownership["launcher_game_id"] == "730"
    assert ownership["processes"] == [new]

    assert (
        ownership["workload_observation"][
            "authority_type"
        ]
        == "customer_game_workload_observation"
    )

    assert "launch_request_ownership" not in ownership


def test_y44e_wrong_session_cannot_be_adopted():
    wrong = ident(
        200,
        2000,
        session=99,
    )

    with pytest.raises(
        observer.WindowsWorkloadObserverError
    ):
        observer.adopt_customer_workload(
            authority(),
            [wrong],
        )


def test_y44e_outside_install_root_cannot_be_adopted():
    wrong = ident(
        200,
        2000,
        executable=r"C:\Windows\System32\notepad.exe",
    )

    with pytest.raises(
        observer.WindowsWorkloadObserverError
    ):
        observer.adopt_customer_workload(
            authority(),
            [wrong],
        )


def test_y44e_incomplete_identity_fails_closed():
    value = authority()

    monkeypatch_identity = {
        "pid": 200,
    }

    with pytest.raises(
        observer.WindowsWorkloadObserverError
    ):
        observer.adopt_customer_workload(
            value,
            [monkeypatch_identity],
        )


def test_y44e_retired_game_is_clean_but_boundary_verified(
    monkeypatch,
):
    new = ident(200, 2000)

    ownership = observer.adopt_customer_workload(
        authority(),
        [new],
    )

    monkeypatch.setattr(
        wvp,
        "_require_windows",
        lambda: None,
    )

    monkeypatch.setattr(
        wvp,
        "_require_windows",
        lambda: None,
    )

    monkeypatch.setattr(
        wvp,
        "read_process_identity",
        lambda pid: (None, None),
    )

    proof = wvp.inspect_verified_process_ownership(
        ownership
    )

    assert proof["ownership_boundary_verified"] is True
    assert proof["owned_process_count"] == 0
    assert proof["owned_processes"] == []
    assert proof["retired_processes"] == [200]
    assert proof["clean"] is True


def test_y44e_second_play_is_new_generation(
    monkeypatch,
):
    first = ident(200, 2000)

    first_authority = authority()

    first_ownership = observer.adopt_customer_workload(
        first_authority,
        [first],
    )

    monkeypatch.setattr(
        wvp,
        "_require_windows",
        lambda: None,
    )

    monkeypatch.setattr(
        wvp,
        "_require_windows",
        lambda: None,
    )

    monkeypatch.setattr(
        wvp,
        "read_process_identity",
        lambda pid: (None, None),
    )

    first_proof = (
        wvp.inspect_verified_process_ownership(
            first_ownership
        )
    )

    assert first_proof["clean"] is True

    second = ident(300, 3000)

    second_authority = authority(
        baseline=[first]
    )

    monkeypatch.setattr(
        observer,
        "snapshot_game_processes",
        lambda **kwargs: [second],
    )

    discovered = (
        observer.discover_customer_workload_processes(
            second_authority
        )
    )

    assert discovered == [second]

    second_ownership = (
        observer.adopt_customer_workload(
            second_authority,
            discovered,
        )
    )

    assert second_ownership["processes"] == [second]
    assert (
        second_ownership["ownership_type"]
        == "windows_verified_process"
    )


def test_y44e_bad_authority_fails_closed(
    monkeypatch,
):
    value = authority()
    value["authority_type"] = "steam_verified_process_launch_attempt"

    monkeypatch.setattr(
        observer,
        "snapshot_game_processes",
        lambda **kwargs: [],
    )

    with pytest.raises(
        observer.WindowsWorkloadObserverError
    ):
        observer.discover_customer_workload_processes(
            value
        )
