from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from khan_agent import gaming_launchers as gl
from khan_agent import gaming_runtime as gr
from khan_agent.gaming import execute_gaming_job
from khan_agent.gaming_launchers import PreparedGameLaunch


pytestmark = pytest.mark.deployment_safe

SESSION_ID = "7fd9cbd3-4ff9-4a30-8fa4-cbcf41a6ab92"
RUNTIME_ID = f"kc-gaming-{SESSION_ID}"
TITLE_ID = "977c6084-839e-42de-af0e-cdf755083e11"
JOB_ID = "c2b1d4f2-e8f0-4c83-a941-0de7e5649092"
INSTALL_ROOT = r"C:\Games\CS2"


def payload(**overrides):
    value = {
        "session_id": SESSION_ID,
        "runtime_id": RUNTIME_ID,
        "gaming_title_id": TITLE_ID,
        "game_slug": "counter-strike-2",
        "launcher_type": "steam",
        "launcher_game_id": "730",
    }
    value.update(overrides)
    return value


def authority():
    return {
        "schema_version": 1,
        "authority_type": "customer_game_workload_observation",
        "runtime_id": RUNTIME_ID,
        "install_root": INSTALL_ROOT,
        "interactive_session_id": 1,
        "launcher_type": "steam",
        "launcher_game_id": "730",
        "baseline": [],
    }


def ready_state(**overrides):
    value = {
        "schema_version": 2,
        "session_id": SESSION_ID,
        "runtime_id": RUNTIME_ID,
        "status": "running",
        "runtime_stage": "stream_ready",
        "game_slug": "counter-strike-2",
        "launcher_type": "steam",
        "launcher_game_id": "730",
        "game": {"install_path": INSTALL_ROOT},
        "interactive_session": {
            "validated": True,
            "managed": True,
            "session_id": 1,
        },
        "runtime_ownership": gr.no_process_ownership(),
        "workload_observation": {
            "schema_version": 1,
            "generation": 1,
            "state": "armed",
            "authority": authority(),
            "last_observed_processes": [],
        },
    }
    value.update(overrides)
    return value


def write_state(root: Path, state: dict | None = None) -> Path:
    path = gr.GamingRuntimePaths(root).session_file(RUNTIME_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state or ready_state()), encoding="utf-8")
    return path


def prepared():
    return PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={"install_path": INSTALL_ROOT},
        launcher_executable=r"C:\Program Files (x86)\Steam\steam.exe",
    )


def attempt():
    return {
        "schema_version": 2,
        "authority_type": "steam_verified_process_launch_attempt",
        "attempt_id": "attempt-38",
        "runtime_id": RUNTIME_ID,
        "install_root": INSTALL_ROOT,
        "interactive_session_id": 1,
        "launcher_type": "steam",
        "launcher_game_id": "730",
        "baseline": [],
    }


def install_play_mocks(monkeypatch, state_file, calls):
    monkeypatch.setattr(
        gr,
        "discover_customer_workload_processes",
        lambda observed: [],
    )
    monkeypatch.setattr(gr, "prepare_game_launch", lambda value: prepared())
    monkeypatch.setattr(
        gr,
        "build_prepared_launch_attempt_authority",
        lambda value: attempt(),
    )

    def dispatch(value, *, launch_attempt):
        persisted = json.loads(state_file.read_text(encoding="utf-8"))
        assert persisted["launch_attempt"]["attempt_id"] == "attempt-38"
        assert persisted["workload_launch"]["node_job_id"] == JOB_ID
        assert value.runtime_id == RUNTIME_ID
        assert value.expected_session_id == 1
        calls.append("dispatch")
        return {"launcher_pid": 9001, "dispatch_only": True}

    monkeypatch.setattr(gr, "dispatch_prepared_game", dispatch)


def play_job(job_id=JOB_ID, value=None):
    return {
        "id": job_id,
        "job_type": "gaming.workload.play",
        "payload": payload() if value is None else value,
    }


def test_dispatch_recognizes_play_and_persists_before_dispatch(tmp_path, monkeypatch):
    state_file = write_state(tmp_path)
    calls = []
    install_play_mocks(monkeypatch, state_file, calls)

    result = execute_gaming_job(
        play_job(),
        execution_enabled=True,
        state_root=tmp_path,
    )

    assert result.status == "succeeded"
    assert result.result["play_state"] == "dispatched"
    assert calls == ["dispatch"]
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["status"] == "running"
    assert saved["runtime_stage"] == "stream_ready"
    assert saved["runtime_ownership"]["ownership_type"] == "none"
    assert saved["workload_observation"]["state"] == "armed"
    assert saved["workload_launch"]["state"] == "dispatched"


def test_execution_disabled_blocks_play(tmp_path):
    result = execute_gaming_job(
        play_job(),
        execution_enabled=False,
        state_root=tmp_path,
    )
    assert result.status == "blocked"


@pytest.mark.parametrize(
    "job",
    [
        {"id": JOB_ID, "job_type": "gaming.workload.play", "payload": []},
        {"job_type": "gaming.workload.play", "payload": payload()},
        {"id": JOB_ID, "job_type": "gaming.workload.play", "payload": {}},
    ],
)
def test_malformed_play_payload_fails_safely(tmp_path, job):
    result = execute_gaming_job(job, execution_enabled=True, state_root=tmp_path)
    assert result.status == "failed"


def test_missing_runtime_blocks(tmp_path):
    result = execute_gaming_job(
        play_job(), execution_enabled=True, state_root=tmp_path
    )
    assert result.status == "blocked"
    assert "does not exist" in result.error_message


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"status": "stopped"}, "running commercial runtime"),
        ({"runtime_stage": "presentation_ready"}, "stream_ready"),
        ({"workload_observation": None}, "observation authority"),
        (
            {
                "workload_observation": {
                    "schema_version": 1,
                    "generation": 1,
                    "state": "running",
                    "authority": authority(),
                    "last_observed_processes": [],
                }
            },
            "not armed",
        ),
    ],
)
def test_runtime_preconditions_block(tmp_path, monkeypatch, changes, message):
    write_state(tmp_path, ready_state(**changes))
    monkeypatch.setattr(
        gr, "discover_customer_workload_processes", lambda observed: []
    )
    result = execute_gaming_job(
        play_job(), execution_enabled=True, state_root=tmp_path
    )
    assert result.status == "blocked"
    assert message in result.error_message


def test_already_owned_workload_blocks_duplicate_play(tmp_path, monkeypatch):
    state = ready_state(
        runtime_ownership={
            "schema_version": 2,
            "ownership_type": "windows_verified_process",
            "runtime_id": RUNTIME_ID,
        }
    )
    state["workload_observation"]["state"] = "running"
    write_state(tmp_path, state)
    monkeypatch.setattr(
        gr,
        "inspect_verified_process_ownership",
        lambda ownership: {
            "ownership_boundary_verified": True,
            "owned_process_count_remaining": 1,
        },
    )

    result = execute_gaming_job(
        play_job(), execution_enabled=True, state_root=tmp_path
    )
    assert result.status == "blocked"
    assert "already owned" in result.error_message


def test_prelaunch_reconciliation_adopts_and_prevents_dispatch(tmp_path, monkeypatch):
    state_file = write_state(tmp_path)
    process = {
        "pid": 4242,
        "creation_time_100ns": 100,
        "executable": INSTALL_ROOT + r"\cs2.exe",
        "session_id": 1,
    }
    monkeypatch.setattr(
        gr, "discover_customer_workload_processes", lambda observed: [process]
    )
    monkeypatch.setattr(
        gr,
        "adopt_customer_workload",
        lambda observed, processes: {
            "schema_version": 2,
            "ownership_type": "windows_verified_process",
            "runtime_id": RUNTIME_ID,
            "processes": processes,
        },
    )
    monkeypatch.setattr(
        gr,
        "dispatch_prepared_game",
        lambda *args, **kwargs: pytest.fail("duplicate dispatch"),
    )

    result = execute_gaming_job(
        play_job(), execution_enabled=True, state_root=tmp_path
    )
    assert result.status == "blocked"
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["runtime_ownership"]["ownership_type"] == "windows_verified_process"


@pytest.mark.parametrize(
    "injected",
    [
        {"install_path": r"C:\Other"},
        {"executable": r"C:\Other\bad.exe"},
        {"launcher_game_id": "999"},
        {"launcher_type": "other"},
        {"game_slug": "other-game"},
    ],
)
def test_customer_payload_cannot_override_server_authority(
    tmp_path, monkeypatch, injected
):
    write_state(tmp_path)
    monkeypatch.setattr(
        gr, "discover_customer_workload_processes", lambda observed: []
    )
    result = execute_gaming_job(
        play_job(value=payload(**injected)),
        execution_enabled=True,
        state_root=tmp_path,
    )
    assert result.status in {"failed", "blocked"}


def test_same_logical_job_retry_never_dispatches_twice(tmp_path, monkeypatch):
    state_file = write_state(tmp_path)
    calls = []
    install_play_mocks(monkeypatch, state_file, calls)

    first = execute_gaming_job(
        play_job(), execution_enabled=True, state_root=tmp_path
    )
    second = execute_gaming_job(
        play_job(), execution_enabled=True, state_root=tmp_path
    )

    assert first.status == second.status == "succeeded"
    assert second.result["idempotent"] is True
    assert calls == ["dispatch"]


def test_different_job_cannot_bypass_pending_attempt(tmp_path, monkeypatch):
    state_file = write_state(tmp_path)
    calls = []
    install_play_mocks(monkeypatch, state_file, calls)
    execute_gaming_job(play_job(), execution_enabled=True, state_root=tmp_path)

    result = execute_gaming_job(
        play_job(job_id=str(uuid4())),
        execution_enabled=True,
        state_root=tmp_path,
    )
    assert result.status == "blocked"
    assert calls == ["dispatch"]


def test_observer_remains_authoritative_adopter_after_dispatch(tmp_path, monkeypatch):
    state_file = write_state(tmp_path)
    calls = []
    install_play_mocks(monkeypatch, state_file, calls)
    execute_gaming_job(play_job(), execution_enabled=True, state_root=tmp_path)

    process = {
        "pid": 5151,
        "creation_time_100ns": 200,
        "executable": INSTALL_ROOT + r"\cs2.exe",
        "session_id": 1,
    }
    monkeypatch.setattr(
        gr, "discover_customer_workload_processes", lambda observed: [process]
    )
    monkeypatch.setattr(
        gr,
        "adopt_customer_workload",
        lambda observed, processes: {
            "schema_version": 2,
            "ownership_type": "windows_verified_process",
            "runtime_id": RUNTIME_ID,
            "processes": processes,
        },
    )

    outcomes = gr.reconcile_customer_workloads(tmp_path)
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert outcomes[0]["state"] == "running"
    assert saved["runtime_ownership"]["ownership_type"] == "windows_verified_process"
    assert "launch_attempt" not in saved
    assert saved["last_play"]["node_job_id"] == JOB_ID

    retry = execute_gaming_job(
        play_job(), execution_enabled=True, state_root=tmp_path
    )
    assert retry.status == "succeeded"
    assert retry.result["idempotent"] is True
    assert calls == ["dispatch"]


def test_generation_two_can_dispatch(tmp_path, monkeypatch):
    state = ready_state()
    state["workload_observation"]["generation"] = 2
    state_file = write_state(tmp_path, state)
    calls = []
    install_play_mocks(monkeypatch, state_file, calls)

    result = execute_gaming_job(
        play_job(), execution_enabled=True, state_root=tmp_path
    )
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert result.status == "succeeded"
    assert saved["workload_launch"]["generation"] == 2


def test_stream_ready_pending_attempt_uses_existing_recovery_authority(monkeypatch):
    state = ready_state(
        launch_attempt=attempt(),
        workload_launch={
            "node_job_id": JOB_ID,
            "attempt_id": "attempt-38",
            "generation": 1,
            "state": "dispatched",
        },
    )
    monkeypatch.setattr(
        "khan_agent.windows_verified_process.classify_launch_attempt_recovery",
        lambda value: {
            "state": "pending",
            "attempt_id": "attempt-38",
            "processes": [],
        },
    )
    assert gr._inspect_pending_launch_attempt(state)["state"] == "pending"


def test_steam_dispatch_is_session_bound_and_does_not_adopt(monkeypatch):
    calls = []
    monkeypatch.setattr(gl.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        gl,
        "launch_steam_app",
        lambda executable, app_id, **kwargs: calls.append(
            (str(executable), app_id, kwargs)
        ) or {
            "launcher_pid": 7001,
            "runtime_ownership": {
                "ownership_type": "windows_job_object",
            },
        },
    )
    value = prepared()
    value = gl.PreparedGameLaunch(
        **{
            **value.__dict__,
            "runtime_id": RUNTIME_ID,
            "expected_session_id": 1,
        }
    )

    result = gl.dispatch_prepared_game(value, launch_attempt=attempt())

    assert result["dispatch_only"] is True
    assert "runtime_ownership" not in result
    assert (
        result["launch_request_ownership"]["ownership_type"]
        == "windows_job_object"
    )
    assert calls[0][2]["expected_session_id"] == 1
