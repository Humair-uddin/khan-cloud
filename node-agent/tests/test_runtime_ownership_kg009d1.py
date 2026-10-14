from __future__ import annotations

import json
from pathlib import Path

from khan_agent import gaming_runtime
from khan_agent import runtime_ownership
import pytest


@pytest.mark.deployment_safe
def test_d1_windows_job_name_is_runtime_scoped():
    value = runtime_ownership.windows_job_name(
        "kc-gaming-11111111-2222-3333-4444-555555555555"
    )

    assert value.startswith(
        r"Global\KhanCloudGaming_"
    )
    assert "11111111-2222" in value


@pytest.mark.deployment_safe
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


@pytest.mark.deployment_safe
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



def test_d1_stop_then_start_revalidates_game_without_auto_launch(
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
                "execution_backend": "windows_native",
                "streaming_backend": "sunshine",
                "gpu_uuid": "GPU-test",
                "minimum_vram_mb": 8192,
                "game_slug": "counter-strike-2",
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
        "snapshot_game_processes",
        lambda **kwargs: [],
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
            "installed": True,
            "install_path": r"C:\Steam\CS2",
        },
        launcher_executable="steam.exe",
    )

    prepared_calls = []
    launch_calls = []
    order = []

    monkeypatch.setattr(
        gaming_runtime,
        "_establish_presentation_contract",
        lambda _session: (
            order.append("display_contract")
            or {
                "required": True,
                "verified": True,
                "requested_mode": {
                    "width": 1920,
                    "height": 1080,
                    "refresh_hz": 60,
                },
            }
        ),
    )

    def fake_prepare(payload):
        order.append("prepare")
        prepared_calls.append(dict(payload))
        return prepared

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        fake_prepare,
    )

    def forbidden_launch(*args, **kwargs):
        launch_calls.append((args, kwargs))
        raise AssertionError(
            "commercial restart must not auto-launch game"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "launch_prepared_game",
        forbidden_launch,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_verify_stream_readiness",
        lambda **kwargs: {
            "runtime_id": runtime_id,
            "verified": True,
            "display": {
                "required": True,
                "healthy": True,
            },
            "sunshine": {
                "ready": True,
                "authenticated_api": True,
            },
            "ownership": {
                "ownership_boundary_verified": True,
                "owned_process_count": 0,
                "clean": True,
            },
            "launcher_pid": None,
            "workload_process_required": False,
        },
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
    assert launch_calls == []
    assert order == [
        "display_contract",
        "prepare",
    ]

    assert prepared_calls[0]["game_slug"] == (
        "counter-strike-2"
    )
    assert prepared_calls[0]["launcher_type"] == "steam"
    assert prepared_calls[0]["launcher_game_id"] == "730"

    saved = json.loads(
        state_file.read_text(encoding="utf-8")
    )

    assert saved["status"] == "running"
    assert saved["runtime_stage"] == "stream_ready"
    assert (
        saved["presentation_contract"]["verified"]
        is True
    )

    assert saved["game_slug"] == "counter-strike-2"
    assert saved["launcher_type"] == "steam"
    assert saved["launcher_game_id"] == "730"
    assert saved["game"]["app_id"] == "730"

    assert "launch_info" not in saved

    ownership_proof = (
        runtime_ownership.inspect_runtime_ownership(
            saved["runtime_ownership"]
        )
    )

    assert (
        ownership_proof["ownership_boundary_verified"]
        is True
    )
    assert ownership_proof["owned_process_count"] == 0
    assert ownership_proof["clean"] is True


def test_d1_failed_restart_game_preparation_returns_to_stopped(
    tmp_path,
    monkeypatch,
):
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)

    session_id = (
        "11111111-2222-4333-8444-555555555556"
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
                "execution_backend": "windows_native",
                "streaming_backend": "sunshine",
                "gpu_uuid": "GPU-test",
                "minimum_vram_mb": 8192,
                "game_slug": "counter-strike-2",
                "launcher_type": "steam",
                "launcher_game_id": "730",
                "runtime_ownership": {
                    "schema_version": 2,
                    "ownership_type": "terminated",
                    "runtime_id": runtime_id,
                    "ownership_boundary_verified": True,
                    "termination_verified": True,
                    "owned_process_count": 0,
                    "owned_process_count_remaining": 0,
                    "clean": True,
                },
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

    monkeypatch.setattr(
        gaming_runtime,
        "_establish_presentation_contract",
        lambda session: {
            "required": True,
            "verified": True,
            "session_id": session["session_id"],
        },
    )

    launch_calls = []

    def fail_prepare(payload):
        raise gaming_runtime.GameLaunchError(
            "synthetic game preparation failure"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        fail_prepare,
    )

    def forbidden_launch(*args, **kwargs):
        launch_calls.append((args, kwargs))
        raise AssertionError(
            "game must not launch after preparation failure"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "launch_prepared_game",
        forbidden_launch,
    )

    result = gaming_runtime.change_session_state(
        {"session_id": session_id},
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="start",
    )

    assert result.status == "blocked"
    assert "synthetic game preparation failure" in (
        result.error_message
    )
    assert launch_calls == []

    saved = json.loads(
        state_file.read_text(encoding="utf-8")
    )

    assert saved["status"] == "stopped"
    assert saved["runtime_stage"] == "stopped"
    assert "launch_info" not in saved

    assert (
        saved["runtime_ownership"]["ownership_type"]
        == "terminated"
    )
    assert (
        saved["runtime_ownership"]["ownership_boundary_verified"]
        is True
    )
    assert (
        saved["runtime_ownership"]["termination_verified"]
        is True
    )
    assert (
        saved["runtime_ownership"]["owned_process_count_remaining"]
        == 0
    )
    assert saved["runtime_ownership"]["clean"] is True

def test_d1_failed_restart_readiness_persists_terminal_cleanup_proof(
    tmp_path,
    monkeypatch,
):
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True)

    session_id = (
        "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
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
                "runtime_ownership": {
                    "schema_version": 2,
                    "ownership_type": "terminated",
                    "runtime_id": runtime_id,
                    "ownership_boundary_verified": True,
                    "termination_verified": True,
                    "owned_process_count": 0,
                    "owned_process_count_remaining": 0,
                    "clean": True,
                },
                "paired_clients": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        gaming_runtime,
        "snapshot_game_processes",
        lambda **kwargs: [],
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
            "validated": True,
        },
    )
    monkeypatch.setattr(
        gaming_runtime,
        "_establish_presentation_contract",
        lambda session: {
            "required": True,
            "verified": True,
            "session_id": session["session_id"],
        },
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
                "install_path": r"C:\Steam\steamapps\common\Counter-Strike Global Offensive",
            },
            launcher_executable="steam.exe",
        ),
    )

    active_ownership = {
        "schema_version": 2,
        "ownership_type": "windows_job_object",
        "runtime_id": runtime_id,
        "job_name":
            r"Global\KhanCloudGaming_Q28R",
        "root_pid": 4242,
        "supervisor_pid": 3131,
        "boundary_established": True,
    }

    monkeypatch.setattr(
        gaming_runtime,
        "launch_prepared_game",
        lambda value, **kwargs: {
            "launcher_pid": 4242,
            "runtime_ownership": active_ownership,
        },
    )

    def fail_readiness(**kwargs):
        raise gaming_runtime.GamingRuntimeError(
            "synthetic readiness failure"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "_verify_stream_readiness",
        fail_readiness,
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_cleanup_failed_launch",
        lambda ownership: {
            "verified": True,
            "runtime_ownership": {
                "ownership_boundary_verified": True,
                "owned_process_count_remaining": 0,
            },
            "termination_proof": {
                "ownership_type": "terminated",
                "owned_processes_before": [4242],
                "owned_processes_remaining": [],
                "owned_process_count_before": 1,
                "owned_process_count_remaining": 0,
                "termination_verified": True,
                "ownership_boundary_verified": True,
                "clean": True,
            },
            "error": None,
        },
    )

    result = gaming_runtime.change_session_state(
        {"session_id": session_id},
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="start",
    )

    assert result.status == "blocked"
    assert "synthetic readiness failure" in (
        result.error_message
    )

    saved = json.loads(
        state_file.read_text(encoding="utf-8")
    )

    assert saved["status"] == "stopped"
    assert saved["runtime_stage"] == "stopped"
    assert "launch_info" not in saved
    assert "launch_attempt" not in saved
    assert "launch_failure" not in saved
    assert "pre_launch_runtime_ownership" not in saved
    assert (
        saved["runtime_ownership"]["ownership_type"]
        == "terminated"
    )
    assert (
        saved["runtime_ownership"][
            "ownership_boundary_verified"
        ]
        is True
    )
    assert (
        saved["runtime_ownership"]["termination_verified"]
        is True
    )
    assert (
        saved["runtime_ownership"][
            "owned_process_count_remaining"
        ]
        == 0
    )
    assert saved["runtime_ownership"]["clean"] is True

    duplicate_stop = gaming_runtime.change_session_state(
        {"session_id": session_id},
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="stop",
    )

    assert duplicate_stop.status == "succeeded"
    assert duplicate_stop.result["idempotent"] is True


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

    # STOP performs the one destructive ownership operation.
    # DELETE consumes the durable verified terminal proof and must
    # never attempt to terminate that already-destroyed boundary.
    assert len(termination_inputs) == 1

    assert (
        termination_inputs[0][
            "ownership_type"
        ]
        == "windows_job"
    )


def test_d1_delete_accepts_verified_persisted_terminated_proof_without_retermination(
    tmp_path,
    monkeypatch,
):
    """Regression for KG-009D3 live KC-01 stop -> delete defect.

    STOP persists ownership_type=terminated after proving the
    structural boundary empty. DELETE must validate that terminal
    evidence instead of passing it back to the active ownership
    terminator, which deliberately does not accept terminated as an
    ownership mechanism.
    """
    state_root = tmp_path / "gaming"
    sessions = state_root / "sessions"
    sessions.mkdir(parents=True)

    session_id = (
        "22345678-1234-4234-8234-123456789abc"
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
                "paired_clients": [],
                "runtime_ownership": {
                    "schema_version": 2,
                    "ownership_type":
                        "terminated",
                    "runtime_id":
                        runtime_id,
                    "ownership_boundary_verified":
                        True,
                    "termination_verified":
                        True,
                    "owned_process_count": 0,
                    "owned_process_count_remaining":
                        0,
                    "clean": True,
                },
            }
        ),
        encoding="utf-8",
    )

    def must_not_reterminate(ownership):
        raise AssertionError(
            "DELETE attempted to re-terminate "
            "persisted terminal ownership evidence"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "terminate_runtime_ownership",
        must_not_reterminate,
    )

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

    sanitation = delete.result[
        "sanitization"
    ]

    assert sanitation["sanitized"] is True
    assert (
        sanitation[
            "runtime_state_deleted"
        ]
        is True
    )

    proof = sanitation[
        "runtime_ownership"
    ]

    assert (
        proof["ownership_type"]
        == "terminated"
    )
    assert (
        proof[
            "ownership_boundary_verified"
        ]
        is True
    )
    assert (
        proof["termination_verified"]
        is True
    )
    assert (
        proof[
            "owned_process_count_remaining"
        ]
        == 0
    )
    assert proof["clean"] is True
    assert (
        proof["already_terminated"]
        is True
    )


def test_d1_delete_rejects_unverified_terminated_proof(
    tmp_path,
):
    """Terminal evidence remains fail closed when incomplete."""
    state_root = tmp_path / "gaming"
    sessions = state_root / "sessions"
    sessions.mkdir(parents=True)

    session_id = (
        "32345678-1234-4234-8234-123456789abc"
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
                "paired_clients": [],
                "runtime_ownership": {
                    "schema_version": 2,
                    "ownership_type":
                        "terminated",
                    "runtime_id":
                        runtime_id,
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

    delete = gaming_runtime.change_session_state(
        {
            "session_id": session_id,
        },
        state_root=state_root,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="delete",
    )

    assert delete.status == "blocked"
    assert state_file.exists()
    assert (
        "Unsupported runtime ownership type: terminated"
        in delete.error_message
    )


def test_d1_established_windows_job_absence_is_verified_clean(
    monkeypatch,
):
    ownership = {
        "schema_version": 2,
        "ownership_type": "windows_job_object",
        "job_name": r"Global\KhanCloudGaming-test",
        "boundary_established": True,
    }

    def missing_job(job_name):
        raise runtime_ownership.RuntimeOwnershipError(
            "OpenJobObjectW failed for "
            f"{job_name}: WinError 2"
        )

    monkeypatch.setattr(
        runtime_ownership,
        "query_windows_job_processes",
        missing_job,
    )

    result = runtime_ownership.inspect_runtime_ownership(
        ownership
    )

    assert result["ownership_boundary_verified"] is True
    assert result["ownership_boundary_retired"] is True
    assert result["owned_process_count"] == 0
    assert result["clean"] is True


def test_d1_unestablished_windows_job_absence_remains_unverified(
    monkeypatch,
):
    ownership = {
        "schema_version": 2,
        "ownership_type": "windows_job_object",
        "job_name": r"Global\KhanCloudGaming-test",
        "boundary_established": False,
    }

    def missing_job(job_name):
        raise runtime_ownership.RuntimeOwnershipError(
            "OpenJobObjectW failed for "
            f"{job_name}: WinError 2"
        )

    monkeypatch.setattr(
        runtime_ownership,
        "query_windows_job_processes",
        missing_job,
    )

    result = runtime_ownership.inspect_runtime_ownership(
        ownership
    )

    assert result["ownership_boundary_verified"] is False
    assert result["clean"] is False
    assert "WinError 2" in result["error"]
    assert "ownership_boundary_retired" not in result


def test_d1_established_windows_job_other_error_remains_unverified(
    monkeypatch,
):
    ownership = {
        "schema_version": 2,
        "ownership_type": "windows_job_object",
        "job_name": r"Global\KhanCloudGaming-test",
        "boundary_established": True,
    }

    def inaccessible_job(job_name):
        raise runtime_ownership.RuntimeOwnershipError(
            "OpenJobObjectW failed for "
            f"{job_name}: WinError 5"
        )

    monkeypatch.setattr(
        runtime_ownership,
        "query_windows_job_processes",
        inaccessible_job,
    )

    result = runtime_ownership.inspect_runtime_ownership(
        ownership
    )

    assert result["ownership_boundary_verified"] is False
    assert result["clean"] is False
    assert "WinError 5" in result["error"]
    assert "ownership_boundary_retired" not in result


def test_d1_terminate_established_absent_windows_job_is_verified(monkeypatch):
    ownership = {
        "schema_version": 2,
        "ownership_type": "windows_job_object",
        "job_name": r"Global\KhanCloudGaming_test",
        "boundary_established": True,
    }

    def absent(_job_name):
        raise runtime_ownership.RuntimeOwnershipError(
            "OpenJobObjectW failed for "
            "Global\\KhanCloudGaming_test: WinError 2"
        )

    monkeypatch.setattr(
        runtime_ownership,
        "terminate_windows_job",
        absent,
    )

    proof = runtime_ownership.terminate_runtime_ownership(
        ownership
    )

    assert proof["ownership_type"] == "terminated"
    assert proof["ownership_boundary_verified"] is True
    assert proof["termination_verified"] is True
    assert proof["owned_process_count_remaining"] == 0
    assert proof["clean"] is True
    assert proof["ownership_boundary_retired"] is True


def test_d1_terminate_unestablished_absent_windows_job_fails_closed(monkeypatch):
    ownership = {
        "schema_version": 2,
        "ownership_type": "windows_job_object",
        "job_name": r"Global\KhanCloudGaming_test",
        "boundary_established": False,
    }

    def absent(_job_name):
        raise runtime_ownership.RuntimeOwnershipError(
            "OpenJobObjectW failed for "
            "Global\\KhanCloudGaming_test: WinError 2"
        )

    monkeypatch.setattr(
        runtime_ownership,
        "terminate_windows_job",
        absent,
    )

    with pytest.raises(runtime_ownership.RuntimeOwnershipError):
        runtime_ownership.terminate_runtime_ownership(ownership)


def test_d1_terminate_established_other_error_fails_closed(monkeypatch):
    ownership = {
        "schema_version": 2,
        "ownership_type": "windows_job_object",
        "job_name": r"Global\KhanCloudGaming_test",
        "boundary_established": True,
    }

    def denied(_job_name):
        raise runtime_ownership.RuntimeOwnershipError(
            "OpenJobObjectW failed for "
            "Global\\KhanCloudGaming_test: WinError 5"
        )

    monkeypatch.setattr(
        runtime_ownership,
        "terminate_windows_job",
        denied,
    )

    with pytest.raises(runtime_ownership.RuntimeOwnershipError):
        runtime_ownership.terminate_runtime_ownership(ownership)


@pytest.mark.deployment_safe
def test_d1_inspect_verified_terminated_proof_is_clean():
    proof = {
        "schema_version": 2,
        "ownership_type": "terminated",
        "ownership_boundary_verified": True,
        "termination_verified": True,
        "owned_process_count": 0,
        "owned_process_count_remaining": 0,
        "clean": True,
    }

    result = runtime_ownership.inspect_runtime_ownership(proof)

    assert result["ownership_type"] == "terminated"
    assert result["ownership_boundary_verified"] is True
    assert result["ownership_boundary_retired"] is True
    assert result["termination_verified"] is True
    assert result["owned_process_count"] == 0
    assert result["clean"] is True


@pytest.mark.deployment_safe
def test_d1_inspect_unverified_terminated_proof_fails_closed():
    proof = {
        "schema_version": 2,
        "ownership_type": "terminated",
        "ownership_boundary_verified": True,
        "termination_verified": False,
        "owned_process_count_remaining": 0,
        "clean": True,
    }

    result = runtime_ownership.inspect_runtime_ownership(proof)

    assert result["ownership_boundary_verified"] is False
    assert result["clean"] is False
    assert result["error"] == "terminated_ownership_proof_unverified"


@pytest.mark.deployment_safe
def test_d1_inspect_terminated_proof_with_remaining_processes_fails_closed():
    proof = {
        "schema_version": 2,
        "ownership_type": "terminated",
        "ownership_boundary_verified": True,
        "termination_verified": True,
        "owned_process_count_remaining": 1,
        "clean": True,
    }

    result = runtime_ownership.inspect_runtime_ownership(proof)

    assert result["ownership_boundary_verified"] is False
    assert result["clean"] is False


@pytest.mark.deployment_safe
def test_d1_inspect_legacy_terminated_proof_fails_closed():
    proof = {
        "schema_version": 1,
        "ownership_type": "terminated",
        "ownership_boundary_verified": True,
        "termination_verified": True,
        "owned_process_count_remaining": 0,
        "clean": True,
    }

    result = runtime_ownership.inspect_runtime_ownership(proof)

    assert result["ownership_boundary_verified"] is False
    assert result["clean"] is False
