from __future__ import annotations

import json
from pathlib import Path

import pytest

from khan_agent import gaming_runtime


def _ownership() -> dict:
    return {
        "ownership_type": "windows_job_object",
        "job_name": r"Global\KhanCloudGaming-test",
        "ownership_boundary_verified": True,
    }


def _state() -> dict:
    return {
        "schema_version": 2,
        "runtime_id": "kc-gaming-test",
        "session_id": "11111111-1111-4111-8111-111111111111",
        "status": "cleanup_required",
        "runtime_stage": "cleanup_required",
        "runtime_ownership": _ownership(),
        "launch_info": {
            "launcher_pid": 4242,
        },
        "paired_clients": [],
        "cleanup": {
            "verified": False,
        },
    }


def _write_runtime_state(
    root: Path,
    state: dict,
) -> Path:
    paths = gaming_runtime.GamingRuntimePaths(root)

    paths.sessions_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        paths.sessions_dir
        / f"{state['runtime_id']}.json"
    )

    path.write_text(
        json.dumps(state),
        encoding="utf-8",
    )

    return path


def test_start_refuses_unresolved_cleanup_required(
    tmp_path,
    monkeypatch,
):
    path = _write_runtime_state(
        tmp_path,
        _state(),
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_state_paths",
        lambda root, session_id: (
            gaming_runtime.GamingRuntimePaths(root),
            "kc-gaming-test",
            path,
        ),
    )

    result = gaming_runtime.change_session_state(
        {
            "session_id": "11111111-1111-4111-8111-111111111111",
        },
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="start",
    )

    assert result.status == "blocked"
    assert (
        "requires verified cleanup"
        in result.error_message
    )
    assert result.result == {}

    persisted = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert persisted["status"] == "cleanup_required"
    assert persisted["runtime_stage"] == "cleanup_required"
    assert "launch_info" in persisted


def test_reconcile_cleanup_required_verified_clean(
    tmp_path,
    monkeypatch,
):
    path = _write_runtime_state(
        tmp_path,
        _state(),
    )

    monkeypatch.setattr(
        gaming_runtime,
        "inspect_runtime_ownership",
        lambda ownership: {
            "ownership_boundary_verified": True,
            "owned_process_count": 1,
            "clean": False,
        },
    )

    proof = {
        "ownership_type": "windows_job_object",
        "job_name": r"Global\KhanCloudGaming-test",
        "ownership_boundary_verified": True,
        "termination_verified": True,
        "owned_process_count_remaining": 0,
    }

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        lambda ownership: proof,
    )

    outcomes = (
        gaming_runtime.reconcile_runtime_ownership(
            tmp_path
        )
    )

    persisted = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert outcomes == [
        {
            "runtime_id": "kc-gaming-test",
            "state": "cleanup_completed",
        }
    ]

    assert persisted["status"] == "stopped"
    assert persisted["runtime_stage"] == "stopped"

    assert (
        persisted["runtime_ownership"][
            "ownership_boundary_verified"
        ]
        is True
    )

    assert (
        persisted["runtime_ownership"][
            "termination_verified"
        ]
        is True
    )

    assert (
        persisted["runtime_ownership"][
            "owned_process_count_remaining"
        ]
        == 0
    )

    assert persisted["cleanup"]["verified"] is True
    assert "launch_info" not in persisted


def test_reconcile_cleanup_required_unverified_stays_blocked(
    tmp_path,
    monkeypatch,
):
    path = _write_runtime_state(
        tmp_path,
        _state(),
    )

    monkeypatch.setattr(
        gaming_runtime,
        "inspect_runtime_ownership",
        lambda ownership: {
            "ownership_boundary_verified": True,
            "owned_process_count": 1,
            "clean": False,
        },
    )

    proof = {
        "ownership_type": "windows_job_object",
        "job_name": r"Global\KhanCloudGaming-test",
        "ownership_boundary_verified": True,
        "termination_verified": False,
        "owned_process_count_remaining": 1,
    }

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        lambda ownership: proof,
    )

    outcomes = (
        gaming_runtime.reconcile_runtime_ownership(
            tmp_path
        )
    )

    persisted = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert outcomes == [
        {
            "runtime_id": "kc-gaming-test",
            "state": "cleanup_required",
        }
    ]

    assert persisted["status"] == "cleanup_required"
    assert persisted["runtime_stage"] == "cleanup_required"
    assert persisted["cleanup"]["verified"] is False

    assert (
        persisted["cleanup"][
            "termination_proof"
        ]["termination_verified"]
        is False
    )

    assert (
        persisted["cleanup"][
            "termination_proof"
        ]["owned_process_count_remaining"]
        == 1
    )

    assert "launch_info" in persisted


def test_reconcile_cleanup_required_termination_error_stays_blocked(
    tmp_path,
    monkeypatch,
):
    path = _write_runtime_state(
        tmp_path,
        _state(),
    )

    monkeypatch.setattr(
        gaming_runtime,
        "inspect_runtime_ownership",
        lambda ownership: {
            "ownership_boundary_verified": True,
            "owned_process_count": 1,
            "clean": False,
        },
    )

    def fail_termination(ownership):
        raise RuntimeError(
            "synthetic termination failure"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        fail_termination,
    )

    outcomes = (
        gaming_runtime.reconcile_runtime_ownership(
            tmp_path
        )
    )

    persisted = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert outcomes == [
        {
            "runtime_id": "kc-gaming-test",
            "state": "cleanup_required",
        }
    ]

    assert persisted["status"] == "cleanup_required"
    assert persisted["runtime_stage"] == "cleanup_required"
    assert "launch_info" in persisted

    reconciliation = persisted[
        "runtime_reconciliation"
    ]

    assert reconciliation["state"] == "cleanup_required"

    assert (
        reconciliation["reason"]
        == "cleanup_termination_failed"
    )

    assert (
        "synthetic termination failure"
        in reconciliation["error"]
    )
