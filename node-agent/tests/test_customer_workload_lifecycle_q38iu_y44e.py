from __future__ import annotations

import json
from pathlib import Path

import pytest

from khan_agent import gaming_runtime as gr
from khan_agent import windows_workload_observer as observer


def _identity(
    pid: int,
    creation: int,
) -> dict:
    return {
        "pid": pid,
        "creation_time_100ns": creation,
        "executable": (
            r"C:\Games\CS2\game\bin\win64\cs2.exe"
        ),
        "session_id": 1,
    }


def _authority() -> dict:
    return observer.make_workload_observation_authority(
        runtime_id="kc-gaming-test",
        install_root=r"C:\Games\CS2",
        expected_session_id=1,
        launcher_type="steam",
        launcher_game_id="730",
        baseline=[],
    )


def _ready_state() -> dict:
    return {
        "session_id": "session-test",
        "runtime_id": "kc-gaming-test",
        "status": "running",
        "runtime_stage": "stream_ready",
        "game_slug": "counter-strike-2",
        "launcher_type": "steam",
        "launcher_game_id": "730",
        "runtime_ownership":
            gr.no_process_ownership(),
        "workload_observation": {
            "schema_version": 1,
            "generation": 1,
            "state": "armed",
            "authority": _authority(),
            "last_observed_processes": [],
        },
    }


def test_y44e_ready_no_play_remains_armed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _ready_state()

    monkeypatch.setattr(
        gr,
        "discover_customer_workload_processes",
        lambda authority: [],
    )

    updated, outcome = (
        gr._reconcile_customer_workload_state(state)
    )

    assert outcome["changed"] is False
    assert outcome["state"] == "armed"
    assert outcome["generation"] == 1
    assert (
        updated["runtime_ownership"]["ownership_type"]
        == "none"
    )
    assert (
        updated["workload_observation"]["state"]
        == "armed"
    )


def test_y44e_first_customer_play_adopts_d1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _ready_state()
    process = _identity(41001, 1001)

    monkeypatch.setattr(
        gr,
        "discover_customer_workload_processes",
        lambda authority: [process],
    )

    def adopt(authority, processes):
        assert authority["runtime_id"] == "kc-gaming-test"
        assert processes == [process]
        return {
            "schema_version": 2,
            "ownership_type": "windows_verified_process",
            "ownership_boundary_established": True,
            "runtime_id": "kc-gaming-test",
            "processes": [process],
        }

    monkeypatch.setattr(
        gr,
        "adopt_customer_workload",
        adopt,
    )

    updated, outcome = (
        gr._reconcile_customer_workload_state(state)
    )

    assert outcome["changed"] is True
    assert outcome["state"] == "running"
    assert outcome["generation"] == 1
    assert outcome["owned_process_count"] == 1

    assert (
        updated["runtime_ownership"]["ownership_type"]
        == "windows_verified_process"
    )
    assert (
        updated["workload_observation"]["state"]
        == "running"
    )


def test_y44e_live_d1_remains_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _ready_state()
    process = _identity(41001, 1001)

    state["runtime_ownership"] = {
        "schema_version": 2,
        "ownership_type": "windows_verified_process",
        "ownership_boundary_established": True,
        "runtime_id": "kc-gaming-test",
        "processes": [process],
    }
    state["workload_observation"]["state"] = "running"

    monkeypatch.setattr(
        gr,
        "inspect_verified_process_ownership",
        lambda ownership: {
            "ownership_boundary_verified": True,
            "owned_process_count_remaining": 1,
            "clean": False,
        },
    )

    updated, outcome = (
        gr._reconcile_customer_workload_state(state)
    )

    assert outcome["changed"] is False
    assert outcome["state"] == "running"
    assert outcome["generation"] == 1
    assert outcome["owned_process_count"] == 1
    assert updated["status"] == "running"
    assert updated["runtime_stage"] == "stream_ready"


def test_y44e_game_exit_rearms_next_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _ready_state()
    process = _identity(41001, 1001)

    state["runtime_ownership"] = {
        "schema_version": 2,
        "ownership_type": "windows_verified_process",
        "ownership_boundary_established": True,
        "runtime_id": "kc-gaming-test",
        "processes": [process],
    }
    state["workload_observation"]["state"] = "running"

    monkeypatch.setattr(
        gr,
        "inspect_verified_process_ownership",
        lambda ownership: {
            "ownership_boundary_verified": True,
            "owned_process_count_remaining": 0,
            "clean": True,
        },
    )

    monkeypatch.setattr(
        gr,
        "snapshot_game_processes",
        lambda **kwargs: [],
    )

    updated, outcome = (
        gr._reconcile_customer_workload_state(state)
    )

    assert outcome["changed"] is True
    assert outcome["state"] == "armed"
    assert outcome["generation"] == 2
    assert outcome["previous_generation_retired"] is True

    assert updated["status"] == "running"
    assert updated["runtime_stage"] == "stream_ready"
    assert (
        updated["runtime_ownership"]["ownership_type"]
        == "none"
    )
    assert (
        updated["workload_observation"]["generation"]
        == 2
    )
    assert (
        updated["workload_observation"]["state"]
        == "armed"
    )


def test_y44e_second_play_is_new_d1_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _ready_state()
    state["workload_observation"]["generation"] = 2

    second = _identity(42002, 2002)

    monkeypatch.setattr(
        gr,
        "discover_customer_workload_processes",
        lambda authority: [second],
    )

    monkeypatch.setattr(
        gr,
        "adopt_customer_workload",
        lambda authority, processes: {
            "schema_version": 2,
            "ownership_type": "windows_verified_process",
            "ownership_boundary_established": True,
            "runtime_id": "kc-gaming-test",
            "processes": list(processes),
        },
    )

    updated, outcome = (
        gr._reconcile_customer_workload_state(state)
    )

    assert outcome["changed"] is True
    assert outcome["state"] == "running"
    assert outcome["generation"] == 2

    assert (
        updated["runtime_ownership"]["processes"][0]["pid"]
        == 42002
    )
    assert (
        updated["runtime_ownership"]["processes"][0][
            "creation_time_100ns"
        ]
        == 2002
    )


def test_y44e_retired_boundary_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _ready_state()

    state["runtime_ownership"] = {
        "schema_version": 2,
        "ownership_type": "windows_verified_process",
        "ownership_boundary_established": True,
        "runtime_id": "kc-gaming-test",
        "processes": [_identity(41001, 1001)],
    }

    monkeypatch.setattr(
        gr,
        "inspect_verified_process_ownership",
        lambda ownership: {
            "ownership_boundary_verified": False,
            "owned_process_count_remaining": 0,
            "clean": False,
        },
    )

    with pytest.raises(
        gr.GamingRuntimeError,
        match="boundary",
    ):
        gr._reconcile_customer_workload_state(state)


def test_y44e_rearm_refuses_unowned_existing_game(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _ready_state()

    monkeypatch.setattr(
        gr,
        "snapshot_game_processes",
        lambda **kwargs: [_identity(43003, 3003)],
    )

    with pytest.raises(
        gr.GamingRuntimeError,
        match="unowned",
    ):
        gr._rearm_customer_workload(state)


def test_y44e_periodic_reconcile_persists_adoption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "gaming"
    paths = gr.GamingRuntimePaths(root)

    state = _ready_state()
    state["runtime_id"] = (
        "kc-gaming-"
        "59f0874e-69c6-4e59-bb46-1bb18e104375"
    )
    state["workload_observation"]["authority"]["runtime_id"] = (
        state["runtime_id"]
    )

    state_file = paths.session_file(state["runtime_id"])
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state),
        encoding="utf-8",
    )

    process = _identity(44004, 4004)

    monkeypatch.setattr(
        gr,
        "discover_customer_workload_processes",
        lambda authority: [process],
    )
    monkeypatch.setattr(
        gr,
        "adopt_customer_workload",
        lambda authority, processes: {
            "schema_version": 2,
            "ownership_type": "windows_verified_process",
            "ownership_boundary_established": True,
            "runtime_id": "kc-gaming-test",
            "processes": list(processes),
        },
    )

    outcomes = gr.reconcile_customer_workloads(root)

    assert len(outcomes) == 1
    assert outcomes[0]["changed"] is True
    assert outcomes[0]["state"] == "running"

    persisted = json.loads(
        state_file.read_text(encoding="utf-8")
    )

    assert (
        persisted["runtime_ownership"]["ownership_type"]
        == "windows_verified_process"
    )
    assert (
        persisted["workload_observation"]["state"]
        == "running"
    )


def test_y44e_periodic_reconcile_ignores_stopped_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "gaming"
    paths = gr.GamingRuntimePaths(root)

    state = _ready_state()
    state["status"] = "stopped"
    state["runtime_id"] = (
        "kc-gaming-"
        "59f0874e-69c6-4e59-bb46-1bb18e104375"
    )
    state["workload_observation"]["authority"]["runtime_id"] = (
        state["runtime_id"]
    )

    state_file = paths.session_file(state["runtime_id"])
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state),
        encoding="utf-8",
    )

    called = {"discover": 0}

    def discover(authority):
        called["discover"] += 1
        return []

    monkeypatch.setattr(
        gr,
        "discover_customer_workload_processes",
        discover,
    )

    outcomes = gr.reconcile_customer_workloads(root)

    assert outcomes == []
    assert called["discover"] == 0


def test_y44e_source_stop_has_final_observation() -> None:
    source = Path(
        gr.__file__
    ).read_text(encoding="utf-8")

    stop_pos = source.index(
        'if action in {"stop", "delete"}:'
    )

    termination_pos = source.index(
        "terminate_runtime_ownership(",
        stop_pos,
    )

    observation_pos = source.index(
        "_reconcile_customer_workload_state(",
        stop_pos,
    )

    assert stop_pos < observation_pos < termination_pos


def test_y44e_source_commercial_start_does_not_launch() -> None:
    import ast

    source = Path(
        gr.__file__
    ).read_text(encoding="utf-8")

    tree = ast.parse(source)

    create = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "create_session"
    )

    launch_calls = []

    for node in ast.walk(create):
        if not isinstance(node, ast.Call):
            continue

        name = (
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else None
        )

        if name == "launch_prepared_game":
            launch_calls.append(node.lineno)

    assert launch_calls == []


def test_y44e_source_heartbeat_owns_recurring_observer() -> None:
    from khan_agent import runtime

    source = Path(
        runtime.__file__
    ).read_text(encoding="utf-8")

    assert (
        "self._reconcile_customer_workloads()"
        in source
    )
    assert (
        "threading.Thread" not in source
        or "customer_workload" not in source
    )
