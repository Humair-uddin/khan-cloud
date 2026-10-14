from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from khan_agent import gaming_runtime


def terminal_proof():
    return {
        "ownership_type":
            "windows_verified_process",
        "ownership_boundary_verified":
            True,
        "termination_verified":
            True,
        "owned_process_count_before":
            1,
        "owned_process_count_remaining":
            0,
        "owned_processes_remaining":
            [],
    }


def recovered_ownership(
    runtime_id="kc-gaming-test",
):
    return {
        "schema_version": 2,
        "ownership_type":
            "windows_verified_process",
        "runtime_id": runtime_id,
        "boundary_established": True,
        "interactive_session_id": 1,
        "install_root":
            r"C:\Steam\steamapps\common\CS2",
        "launcher_type": "steam",
        "launcher_game_id": "730",
        "processes": [
            {
                "pid": 222,
                "creation_time_100ns":
                    2000,
                "session_id": 1,
                "executable":
                    r"C:\Steam\steamapps\common\CS2\cs2.exe",
            }
        ],
    }


def write_pending(tmp_path):
    session_id = str(uuid4())
    runtime_id = (
        f"kc-gaming-{session_id}"
    )

    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)

    path = sessions / f"{runtime_id}.json"

    state = {
        "schema_version": 2,
        "session_id": session_id,
        "runtime_id": runtime_id,
        "status": "starting",
        "runtime_stage":
            "launch_recovery_pending",
        "execution_backend":
            "windows_native",
        "streaming_backend":
            "sunshine",
        "gpu_uuid": "GPU-test",
        "minimum_vram_mb": 8192,
        "paired_clients": [],
        "runtime_ownership": {
            "schema_version": 2,
            "ownership_type":
                "windows_job_object",
            "job_name":
                "Global\\KhanCloudGaming_test",
            "root_pid": None,
            "boundary_established": False,
        },
        "launch_attempt": {
            "schema_version": 2,
            "authority_type":
                "steam_verified_process_launch_attempt",
            "attempt_id": "attempt-test",
            "runtime_id": runtime_id,
            "install_root":
                r"C:\Steam\steamapps\common\CS2",
            "interactive_session_id": 1,
            "launcher_type": "steam",
            "launcher_game_id": "730",
            "created_at_epoch": 1.0,
            "recovery_deadline_epoch": 181.0,
            "recovery_window_seconds": 180.0,
            "baseline": [],
        },
    }

    path.write_text(
        json.dumps(state),
        encoding="utf-8",
    )

    return session_id, runtime_id, path


def read(path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def test_q38iu_start_refuses_pending_attempt(
    tmp_path,
):
    session_id, _, path = (
        write_pending(tmp_path)
    )

    result = (
        gaming_runtime.change_session_state(
            {"session_id": session_id},
            state_root=tmp_path,
            execution_backend=
                "windows_native",
            streaming_backend=
                "sunshine",
            action="start",
        )
    )

    assert result.status == "blocked"
    assert (
        read(path)["runtime_stage"]
        == "launch_recovery_pending"
    )


def test_q38iu_reconcile_pending_candidate_is_sanitized(
    tmp_path,
    monkeypatch,
):
    _, runtime_id, path = (
        write_pending(tmp_path)
    )

    ownership = recovered_ownership(
        runtime_id
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_inspect_pending_launch_attempt",
        lambda state: {
            "state":
                "candidate_discovered",
            "attempt_id":
                "attempt-test",
            "runtime_ownership":
                ownership,
            "processes":
                ownership["processes"],
        },
    )

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        lambda value: terminal_proof(),
    )

    outcomes = (
        gaming_runtime
        .reconcile_runtime_ownership(
            tmp_path
        )
    )

    assert outcomes == [
        {
            "runtime_id": runtime_id,
            "state":
                "late_launch_cleanup_completed",
        }
    ]

    saved = read(path)

    assert saved["status"] == "stopped"
    assert (
        saved["runtime_stage"]
        == "stopped"
    )
    assert (
        saved["runtime_ownership"][
            "ownership_type"
        ]
        == "terminated"
    )
    assert (
        saved["runtime_ownership"][
            "clean"
        ]
        is True
    )
    assert "launch_attempt" not in saved


def test_q38iu_reconcile_failed_late_cleanup_stays_blocked(
    tmp_path,
    monkeypatch,
):
    _, runtime_id, path = (
        write_pending(tmp_path)
    )

    ownership = recovered_ownership(
        runtime_id
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_inspect_pending_launch_attempt",
        lambda state: {
            "state":
                "candidate_discovered",
            "attempt_id":
                "attempt-test",
            "runtime_ownership":
                ownership,
        },
    )

    def fail(value):
        raise RuntimeError(
            "synthetic termination failure"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        fail,
    )

    outcomes = (
        gaming_runtime
        .reconcile_runtime_ownership(
            tmp_path
        )
    )

    assert outcomes[0]["state"] == (
        "cleanup_required"
    )

    saved = read(path)

    assert saved["status"] == (
        "cleanup_required"
    )
    assert saved["runtime_stage"] == (
        "cleanup_required"
    )
    assert (
        saved["runtime_ownership"][
            "ownership_type"
        ]
        == "windows_verified_process"
    )


def test_q38iu_reconcile_no_candidate_remains_pending(
    tmp_path,
    monkeypatch,
):
    _, runtime_id, path = (
        write_pending(tmp_path)
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_inspect_pending_launch_attempt",
        lambda state: {
            "state": "pending",
            "attempt_id":
                "attempt-test",
            "processes": [],
        },
    )

    outcomes = (
        gaming_runtime
        .reconcile_runtime_ownership(
            tmp_path
        )
    )

    assert outcomes == [
        {
            "runtime_id": runtime_id,
            "state":
                "launch_recovery_pending",
        }
    ]

    saved = read(path)

    assert saved["status"] == "starting"
    assert saved["runtime_stage"] == (
        "launch_recovery_pending"
    )
    assert "launch_attempt" in saved


def test_q38iu_reconcile_expired_without_candidate_fails_closed(
    tmp_path,
    monkeypatch,
):
    _, runtime_id, path = (
        write_pending(tmp_path)
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_inspect_pending_launch_attempt",
        lambda state: {
            "state":
                "expired_no_candidate",
            "attempt_id":
                "attempt-test",
            "processes": [],
        },
    )

    outcomes = (
        gaming_runtime
        .reconcile_runtime_ownership(
            tmp_path
        )
    )

    assert outcomes == [
        {
            "runtime_id": runtime_id,
            "state":
                "launch_attempt_expired",
        }
    ]

    saved = read(path)

    assert saved["status"] == (
        "cleanup_required"
    )
    assert "launch_attempt" in saved


def test_q38iu_stop_pending_candidate_terminates_exact_boundary(
    tmp_path,
    monkeypatch,
):
    session_id, runtime_id, path = (
        write_pending(tmp_path)
    )

    ownership = recovered_ownership(
        runtime_id
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_inspect_pending_launch_attempt",
        lambda state: {
            "state":
                "candidate_discovered",
            "attempt_id":
                "attempt-test",
            "runtime_ownership":
                ownership,
        },
    )

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        lambda value: terminal_proof(),
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_validate_windows_native",
        lambda **kwargs: {
            "gpu": {
                "uuid": "GPU-test",
                "memory_total_mib": 10240,
            }
        },
    )

    result = (
        gaming_runtime.change_session_state(
            {"session_id": session_id},
            state_root=tmp_path,
            execution_backend=
                "windows_native",
            streaming_backend=
                "sunshine",
            action="stop",
        )
    )

    assert result.status == "succeeded"

    saved = read(path)

    assert saved["status"] == "stopped"
    assert (
        saved["runtime_ownership"][
            "ownership_type"
        ]
        == "terminated"
    )
    assert "launch_attempt" not in saved


def test_q38iu_stop_pending_without_candidate_refuses_repool(
    tmp_path,
    monkeypatch,
):
    session_id, _, path = (
        write_pending(tmp_path)
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_inspect_pending_launch_attempt",
        lambda state: {
            "state": "pending",
            "attempt_id":
                "attempt-test",
            "processes": [],
        },
    )

    result = (
        gaming_runtime.change_session_state(
            {"session_id": session_id},
            state_root=tmp_path,
            execution_backend=
                "windows_native",
            streaming_backend=
                "sunshine",
            action="stop",
        )
    )

    assert result.status == "blocked"

    saved = read(path)

    assert saved["runtime_stage"] == (
        "launch_recovery_pending"
    )
    assert "launch_attempt" in saved


def test_q38iu_delete_pending_candidate_sanitizes_before_state_removal(
    tmp_path,
    monkeypatch,
):
    session_id, runtime_id, path = (
        write_pending(tmp_path)
    )

    ownership = recovered_ownership(
        runtime_id
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_inspect_pending_launch_attempt",
        lambda state: {
            "state":
                "candidate_discovered",
            "attempt_id":
                "attempt-test",
            "runtime_ownership":
                ownership,
        },
    )

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        lambda value: terminal_proof(),
    )

    result = (
        gaming_runtime.change_session_state(
            {"session_id": session_id},
            state_root=tmp_path,
            execution_backend=
                "windows_native",
            streaming_backend=
                "sunshine",
            action="delete",
        )
    )

    assert result.status == "succeeded"
    assert not path.exists()


def test_q38iu_terminal_normalizer_refuses_false_clean():
    value = (
        gaming_runtime
        ._terminated_ownership_from_proof(
            runtime_id="kc-gaming-test",
            proof={
                "ownership_boundary_verified":
                    True,
                "termination_verified":
                    False,
                "owned_process_count_remaining":
                    1,
            },
            retirement_reason="test",
        )
    )

    assert value["clean"] is False
    assert (
        value["owned_process_count"]
        == 1
    )
