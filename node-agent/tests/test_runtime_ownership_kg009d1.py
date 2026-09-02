from __future__ import annotations

import json
from pathlib import Path

from khan_agent import gaming_runtime
from khan_agent import runtime_ownership


def test_d1_windows_job_name_is_runtime_scoped():
    value = runtime_ownership.windows_job_name(
        "kc-gaming-11111111-2222-3333-4444-555555555555"
    )

    assert value.startswith(
        r"Global\KhanCloudGaming_"
    )
    assert "11111111-2222" in value


def test_d1_none_ownership_is_authoritatively_clean():
    value = runtime_ownership.no_process_ownership()

    proof = runtime_ownership.inspect_runtime_ownership(
        value
    )

    assert proof[
        "ownership_boundary_verified"
    ] is True
    assert proof["owned_process_count"] == 0
    assert proof["clean"] is True


def test_d1_state_writer_fsyncs_before_atomic_replace():
    source = Path(
        gaming_runtime.__file__
    ).read_text()

    writer = source.split(
        "def _write_state(",
        1,
    )[1].split(
        "def _interactive_session_context",
        1,
    )[0]

    assert "os.fsync" in writer
    assert "os.replace" in writer


def test_d1_runtime_schema_v2_contains_structural_ownership():
    source = Path(
        gaming_runtime.__file__
    ).read_text()

    assert '"schema_version": 2' in source
    assert '"runtime_ownership"' in source
    assert "planned_runtime_ownership" in source
    assert "terminate_runtime_ownership" in source


def test_d1_reconciliation_never_process_name_sweeps():
    source = Path(
        gaming_runtime.__file__
    ).read_text().lower()

    reconciliation = source.split(
        "def reconcile_runtime_ownership(",
        1,
    )[1]

    assert "tasklist" not in reconciliation
    assert "get-process" not in reconciliation
    assert "process name" not in reconciliation


def test_d1_reconcile_no_process_runtime(tmp_path):
    sessions = tmp_path / "sessions"
    sessions.mkdir()

    path = sessions / (
        "kc-gaming-11111111-2222-3333-4444-555555555555.json"
    )

    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runtime_id":
                    "kc-gaming-11111111-2222-3333-4444-555555555555",
                "status": "running",
                "runtime_ownership":
                    runtime_ownership.no_process_ownership(),
            }
        ),
        encoding="utf-8",
    )

    outcomes = (
        gaming_runtime.reconcile_runtime_ownership(
            tmp_path
        )
    )

    assert outcomes[0]["state"] == "verified"

    saved = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    assert (
        saved["runtime_reconciliation"]["state"]
        == "verified"
    )


def test_d1_stop_then_start_relaunches_structural_runtime(
    tmp_path,
    monkeypatch,
):
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)

    session_id = (
        "11111111-2222-4333-8444-555555555555"
    )
    runtime_id = f"kc-gaming-{session_id}"
    state_file = sessions / f"{runtime_id}.json"

    state_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "session_id": session_id,
                "runtime_id": runtime_id,
                "status": "stopped",
                "runtime_stage": "stopped",
                "execution_backend":
                    "windows_native",
                "streaming_backend":
                    "sunshine",
                "gpu_uuid": "GPU-test",
                "minimum_vram_mb": 8192,
                "game_slug":
                    "counter-strike-2",
                "launcher_type": "steam",
                "launcher_game_id": "730",
                "launcher": "steam",
                "launcher_app_id": "730",
                "runtime_ownership":
                    runtime_ownership.no_process_ownership(),
                "paired_clients": [],
            }
        ),
        encoding="utf-8",
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
    monkeypatch.setattr(
        gaming_runtime,
        "_interactive_session_context",
        lambda: {
            "session_id": 1,
            "state": "Active",
        },
    )

    from khan_agent.gaming_launchers import (
        PreparedGameLaunch,
    )

    prepared = PreparedGameLaunch(
        game_slug="counter-strike-2",
        launcher_type="steam",
        launcher_game_id="730",
        game={
            "launcher": "steam",
            "app_id": "730",
        },
        launcher_executable="steam.exe",
    )

    prepared_calls = []
    launch_calls = []

    def fake_prepare(payload):
        prepared_calls.append(dict(payload))
        return prepared

    def fake_launch(value):
        launch_calls.append(value)
        return {
            "launcher_pid": 4242,
            "runtime_ownership": {
                "schema_version": 2,
                "ownership_type":
                    "windows_job",
                "runtime_id": runtime_id,
                "job_name":
                    "Global\\\\KhanCloudGaming_test",
                "supervisor_pid": 3131,
                "owned_process_count": 1,
                "ownership_boundary_verified":
                    True,
                "termination_verified": False,
            },
        }

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        fake_prepare,
    )
    monkeypatch.setattr(
        gaming_runtime,
        "launch_prepared_game",
        fake_launch,
    )

    result = gaming_runtime.change_session_state(
        {"session_id": session_id},
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="start",
    )

    assert result.status == "succeeded"
    assert result.result["status"] == "running"
    assert result.result.get("idempotent") is not True
    assert len(prepared_calls) == 1
    assert len(launch_calls) == 1
    assert prepared_calls[0]["game_slug"] == (
        "counter-strike-2"
    )
    assert prepared_calls[0]["launcher_type"] == (
        "steam"
    )
    assert prepared_calls[0][
        "launcher_game_id"
    ] == "730"

    saved = json.loads(
        state_file.read_text(encoding="utf-8")
    )
    assert saved["status"] == "running"
    assert saved["runtime_stage"] == "stream_ready"
    assert saved["launch_info"]["launcher_pid"] == 4242
    assert (
        saved["runtime_ownership"]["ownership_type"]
        == "windows_job"
    )


def test_d1_failed_restart_returns_to_stopped_without_pid_identity(
    tmp_path,
    monkeypatch,
):
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)

    session_id = (
        "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    )
    runtime_id = f"kc-gaming-{session_id}"
    state_file = sessions / f"{runtime_id}.json"

    state_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "session_id": session_id,
                "runtime_id": runtime_id,
                "status": "stopped",
                "runtime_stage": "stopped",
                "gpu_uuid": "GPU-test",
                "minimum_vram_mb": 8192,
                "game_slug":
                    "counter-strike-2",
                "launcher_type": "steam",
                "launcher_game_id": "730",
                "runtime_ownership":
                    runtime_ownership.no_process_ownership(),
                "paired_clients": [],
            }
        ),
        encoding="utf-8",
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
    monkeypatch.setattr(
        gaming_runtime,
        "_interactive_session_context",
        lambda: {"session_id": 1},
    )

    from khan_agent.gaming_launchers import (
        PreparedGameLaunch,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        lambda payload: PreparedGameLaunch(
            game_slug="counter-strike-2",
            launcher_type="steam",
            launcher_game_id="730",
            game={
                "launcher": "steam",
                "app_id": "730",
            },
            launcher_executable="steam.exe",
        ),
    )

    def fail_launch(value):
        raise gaming_runtime.GameLaunchError(
            "synthetic restart failure"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "launch_prepared_game",
        fail_launch,
    )

    result = gaming_runtime.change_session_state(
        {"session_id": session_id},
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="start",
    )

    assert result.status == "blocked"
    assert "synthetic restart failure" in (
        result.error_message
    )

    saved = json.loads(
        state_file.read_text(encoding="utf-8")
    )

    assert saved["status"] == "stopped"
    assert saved["runtime_stage"] == "stopped"
    assert "launch_info" not in saved
    assert (
        saved["runtime_ownership"]["ownership_type"]
        == "none"
    )



def test_d1_legacy_v1_reconciliation_preserves_without_pid_action(
    tmp_path,
    monkeypatch,
):
    state_root = tmp_path / "gaming"
    sessions = state_root / "sessions"
    sessions.mkdir(parents=True)

    runtime_id = "kc-gaming-legacy-pid-reuse"
    state_file = sessions / f"{runtime_id}.json"
    state_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "runtime_id": runtime_id,
                "session_id": "legacy-session",
                "status": "running",
                "launch_info": {
                    "launcher_pid": 20900,
                },
            }
        ),
        encoding="utf-8",
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "legacy reconciliation must not act on recorded PID"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "_terminate_recorded_launcher",
        forbidden,
    )
    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        forbidden,
    )

    outcomes = gaming_runtime.reconcile_runtime_ownership(
        state_root
    )

    assert outcomes == [
        {
            "runtime_id": runtime_id,
            "state": "legacy_v1",
            "action": "preserved",
        }
    ]


def test_d1_legacy_delete_never_terminates_reused_pid(
    tmp_path,
    monkeypatch,
):
    state_root = tmp_path / "gaming"
    sessions = state_root / "sessions"
    sessions.mkdir(parents=True)

    session_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    runtime_id = f"kc-gaming-{session_id}"
    state_file = sessions / f"{runtime_id}.json"

    state_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "runtime_id": runtime_id,
                "session_id": session_id,
                "status": "running",
                "gpu_uuid": "GPU-test",
                "minimum_vram_mb": 8192,
                "launch_info": {
                    "launcher_pid": 20900,
                },
                "paired_clients": [],
            }
        ),
        encoding="utf-8",
    )

    destructive_calls = []

    def forbidden_terminate(pid):
        destructive_calls.append(pid)
        raise AssertionError(
            "legacy delete must not terminate PID-only ownership"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "_terminate_recorded_launcher",
        forbidden_terminate,
    )
    monkeypatch.setattr(
        gaming_runtime,
        "_process_alive",
        lambda pid: True,
    )

    result = gaming_runtime.change_session_state(
        {
            "session_id": session_id,
        },
        state_root=state_root,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert result.status == "blocked"
    assert destructive_calls == []
    assert state_file.exists()
    assert (
        "Legacy runtime process ownership cannot be proven"
        in result.error_message
    )



def test_legacy_retirement_never_uses_recorded_pid_termination():
    from pathlib import Path

    source = Path(
        "khan_agent/gaming_runtime.py"
    ).read_text()

    assert "legacy_schema_v1_retirement" in source
    assert "recorded_pid_identity_reused" in source
    assert "game_process_count" in source
    assert "supervisor_process_count" in source
    assert '"destructive_pid_termination_performed": False' in source


def test_plain_v1_sanitization_shortcut_removed():
    from pathlib import Path

    source = Path(
        "khan_agent/gaming_runtime.py"
    ).read_text()

    assert "legacy_pid_identity_unverifiable" in source
    assert (
        '"ownership_schema_version"\n'
        '                                )\n'
        '                                or 0\n'
        '                            )\n'
        '                            < 2'
        not in source
    )


def test_legacy_retirement_windows_snapshot_uses_powershell_subexpression():
    from pathlib import Path
    import khan_agent.gaming_runtime as runtime

    source = Path(runtime.__file__).read_text()

    assert 'creation_date = $(if ($_.CreationDate)' in source
    assert 'creation_date = (\\n            if ($_.CreationDate)' not in source


def test_legacy_retirement_retry_contract_is_archive_aware():
    from pathlib import Path
    import khan_agent.gaming_runtime as runtime

    source = Path(runtime.__file__).read_text()

    assert 'retry_from_archive' in source
    assert 'archive_file.exists()' in source
    assert 'archive_sha != expected_sha' in source
    assert '_legacy_retirement_evidence(' in source
    assert (
        "Legacy retirement state and authorized"
        in source
    )
    assert "archive are both absent" in source


def test_d1_structural_stop_then_delete_uses_persisted_terminated_proof(
    tmp_path,
    monkeypatch,
):
    state_root = tmp_path / "gaming"
    sessions = state_root / "sessions"
    sessions.mkdir(parents=True)

    session_id = (
        "12345678-1234-4234-8234-123456789abc"
    )
    runtime_id = f"kc-gaming-{session_id}"
    state_file = sessions / f"{runtime_id}.json"

    state_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "session_id": session_id,
                "runtime_id": runtime_id,
                "status": "running",
                "runtime_stage": "stream_ready",
                "execution_backend":
                    "windows_native",
                "streaming_backend":
                    "sunshine",
                "gpu_uuid": "GPU-test",
                "minimum_vram_mb": 8192,
                "paired_clients": [],
                "launch_info": {
                    "launcher_pid": 4242,
                },
                "runtime_ownership": {
                    "schema_version": 2,
                    "ownership_type":
                        "windows_job",
                    "runtime_id":
                        runtime_id,
                    "job_name":
                        "Global\\KhanCloudGaming_test",
                    "ownership_boundary_verified":
                        True,
                    "termination_verified":
                        False,
                    "owned_process_count": 1,
                    "owned_process_count_remaining":
                        1,
                    "clean": False,
                },
            }
        ),
        encoding="utf-8",
    )

    termination_inputs = []

    def fake_terminate(ownership):
        termination_inputs.append(
            dict(ownership)
        )

        return {
            "schema_version": 2,
            "ownership_type":
                str(
                    ownership.get(
                        "ownership_type"
                    )
                ),
            "runtime_id": runtime_id,
            "ownership_boundary_verified":
                True,
            "termination_verified":
                True,
            "owned_process_count_before":
                int(
                    ownership.get(
                        "owned_process_count",
                        0,
                    )
                    or 0
                ),
            "owned_process_count_remaining":
                0,
            "clean": True,
        }

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        fake_terminate,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_process_alive",
        lambda pid: False,
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

    stop = gaming_runtime.change_session_state(
        {
            "session_id": session_id,
        },
        state_root=state_root,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="stop",
    )

    assert stop.status == "succeeded"
    assert state_file.exists()

    stopped = json.loads(
        state_file.read_text(
            encoding="utf-8"
        )
    )

    assert stopped["status"] == "stopped"
    assert stopped["runtime_stage"] == "stopped"
    assert "launch_info" not in stopped

    proof = stopped["runtime_ownership"]

    assert proof["ownership_type"] == "terminated"
    assert (
        proof["ownership_boundary_verified"]
        is True
    )
    assert proof["termination_verified"] is True
    assert proof["owned_process_count"] == 0
    assert (
        proof["owned_process_count_remaining"]
        == 0
    )
    assert proof["clean"] is True

    delete = gaming_runtime.change_session_state(
        {
            "session_id": session_id,
        },
        state_root=state_root,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert delete.status == "succeeded"
    assert delete.result["deleted"] is True
    assert not state_file.exists()

    sanitation = delete.result["sanitization"]

    assert sanitation["sanitized"] is True
    assert (
        sanitation["runtime_state_deleted"]
        is True
    )
    assert (
        sanitation["paired_clients_remaining"]
        == 0
    )
    assert (
        sanitation["recorded_launcher_alive"]
        is False
    )

    delete_proof = sanitation[
        "runtime_ownership"
    ]

    assert (
        delete_proof[
            "ownership_boundary_verified"
        ]
        is True
    )
    assert (
        delete_proof[
            "termination_verified"
        ]
        is True
    )
    assert (
        delete_proof[
            "owned_process_count_remaining"
        ]
        == 0
    )

    assert len(termination_inputs) == 2

    assert (
        termination_inputs[0][
            "ownership_type"
        ]
        == "windows_job"
    )

    assert (
        termination_inputs[1][
            "ownership_type"
        ]
        == "terminated"
    )
