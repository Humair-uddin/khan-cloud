from pathlib import Path
from uuid import uuid4

from khan_agent import gaming_runtime
from khan_agent import runtime_ownership
from khan_agent.job_dispatch import execute_node_job


COMMON = {
    "virtualization_execution_enabled": False,
    "virtualization_storage_root": Path("/tmp/kc-vps"),
    "virtualization_base_image_path": Path("/tmp/base.qcow2"),
    "virtualization_network_name": "kc-test",
    "gaming_execution_enabled": True,
    "gaming_execution_backend": "windows_native",
    "gaming_streaming_backend": "sunshine",
}


def _good_environment(monkeypatch):
    class ManagedSession:
        session_id = 1
        available = True
        source = "test"
        managed = True
        username = "KhanGaming"
        broker_mode = "managed_autologon"

    monkeypatch.setattr(
        gaming_runtime,
        "require_interactive_session",
        lambda **kwargs: ManagedSession(),
    )
    monkeypatch.setattr(
        gaming_runtime,
        "_establish_presentation_contract",
        lambda session: {
            "required": True,
            "verified": True,
            "session_id": session.get("session_id"),
            "requested_mode": {
                "width": 1920,
                "height": 1080,
                "refresh_hz": 60,
            },
        },
    )

    monkeypatch.setattr(gaming_runtime, "locate_sunshine", lambda: Path("/sunshine.exe"))
    monkeypatch.setattr(
        gaming_runtime,
        "probe_nvidia_gpu",
        lambda gpu_uuid: {
            "available": True,
            "uuid": gpu_uuid,
            "name": "NVIDIA RTX Test",
            "memory_total_mib": 12288,
            "driver_version": "595.95",
        },
    )

    monkeypatch.setattr(
        gaming_runtime,
        "probe_sunshine_readiness",
        lambda **kwargs: {
            "ready": True,
            "authenticated_api": True,
            "endpoint": "/api/clients/list",
        },
    )


def _job(job_type, session_id, **payload):
    return {
        "job_type": job_type,
        "payload": {"session_id": str(session_id), **payload},
    }


def test_create_persists_runtime_and_returns_safe_connection_contract(tmp_path, monkeypatch):
    _good_environment(monkeypatch)
    session_id = uuid4()
    result = execute_node_job(
        _job(
            "gaming.session.create",
            session_id,
            gpu_uuid="GPU-TEST",
            minimum_vram_mb=8192,
            streaming_backend="sunshine",
        ),
        gaming_state_root=tmp_path,
        **COMMON,
    )
    assert result.status == "succeeded"
    assert result.result["runtime_id"] == f"kc-gaming-{session_id}"
    assert result.result["connection_info"]["ready"] is True
    assert result.result["connection_info"]["protocol"] == "moonlight"
    assert result.result["connection_info"]["credential_mode"] == "control_plane_pending"
    state_file = tmp_path / "sessions" / f"kc-gaming-{session_id}.json"
    assert state_file.exists()
    assert "password" not in state_file.read_text().lower()


def test_create_is_idempotent_and_never_reassigns_existing_runtime(tmp_path, monkeypatch):
    _good_environment(monkeypatch)
    session_id = uuid4()
    job = _job("gaming.session.create", session_id, gpu_uuid="GPU-A", minimum_vram_mb=8192)
    first = execute_node_job(job, gaming_state_root=tmp_path, **COMMON)
    second = execute_node_job(job, gaming_state_root=tmp_path, **COMMON)
    assert first.status == second.status == "succeeded"
    assert second.result["idempotent"] is True
    changed = execute_node_job(
        _job("gaming.session.create", session_id, gpu_uuid="GPU-B", minimum_vram_mb=8192),
        gaming_state_root=tmp_path,
        **COMMON,
    )
    assert changed.status == "blocked"
    assert "different GPU" in changed.error_message


def test_create_rejects_less_than_8gb_even_if_backend_payload_is_bad(tmp_path, monkeypatch):
    _good_environment(monkeypatch)
    result = execute_node_job(
        _job("gaming.session.create", uuid4(), gpu_uuid="GPU-A", minimum_vram_mb=4096),
        gaming_state_root=tmp_path,
        **COMMON,
    )
    assert result.status == "failed"
    assert "8192" in result.error_message


def test_create_rechecks_actual_assigned_gpu_vram(tmp_path, monkeypatch):
    monkeypatch.setattr(gaming_runtime, "locate_sunshine", lambda: Path("/sunshine.exe"))
    monkeypatch.setattr(
        gaming_runtime,
        "probe_nvidia_gpu",
        lambda gpu_uuid: {"available": True, "uuid": gpu_uuid, "memory_total_mib": 6144},
    )
    result = execute_node_job(
        _job("gaming.session.create", uuid4(), gpu_uuid="GPU-A", minimum_vram_mb=8192),
        gaming_state_root=tmp_path,
        **COMMON,
    )
    assert result.status == "blocked"
    assert "6144" in result.error_message


def test_missing_sunshine_fails_closed_without_installing_anything(tmp_path, monkeypatch):
    monkeypatch.setattr(gaming_runtime, "locate_sunshine", lambda: None)
    monkeypatch.setattr(gaming_runtime, "probe_nvidia_gpu", lambda _: {"available": True, "memory_total_mib": 12288})
    result = execute_node_job(
        _job("gaming.session.create", uuid4(), gpu_uuid="GPU-A", minimum_vram_mb=8192),
        gaming_state_root=tmp_path,
        **COMMON,
    )
    assert result.status == "blocked"
    assert "will not install or replace" in result.error_message


def test_lifecycle_is_stateful_idempotent_and_delete_is_safe(tmp_path, monkeypatch):
    _good_environment(monkeypatch)
    session_id = uuid4()
    create = execute_node_job(
        _job("gaming.session.create", session_id, gpu_uuid="GPU-A", minimum_vram_mb=8192),
        gaming_state_root=tmp_path,
        **COMMON,
    )
    assert create.status == "succeeded"
    stop = execute_node_job(_job("gaming.session.stop", session_id), gaming_state_root=tmp_path, **COMMON)
    assert stop.status == "succeeded" and stop.result["status"] == "stopped"
    stop2 = execute_node_job(_job("gaming.session.stop", session_id), gaming_state_root=tmp_path, **COMMON)
    assert stop2.result["idempotent"] is True
    start = execute_node_job(_job("gaming.session.start", session_id), gaming_state_root=tmp_path, **COMMON)
    assert start.status == "succeeded" and start.result["status"] == "running"
    delete = execute_node_job(_job("gaming.session.delete", session_id), gaming_state_root=tmp_path, **COMMON)
    assert delete.status == "succeeded" and delete.result["deleted"] is True
    delete2 = execute_node_job(_job("gaming.session.delete", session_id), gaming_state_root=tmp_path, **COMMON)
    assert delete2.status == "succeeded" and delete2.result["idempotent"] is True


def test_execution_disabled_blocks_mutating_gaming_jobs(tmp_path):
    result = execute_node_job(
        _job("gaming.session.create", uuid4(), gpu_uuid="GPU-A", minimum_vram_mb=8192),
        gaming_execution_enabled=False,
        gaming_execution_backend="windows_native",
        gaming_streaming_backend="sunshine",
        gaming_state_root=tmp_path,
        virtualization_execution_enabled=False,
        virtualization_storage_root=Path("/tmp/kc-vps"),
        virtualization_base_image_path=Path("/tmp/base.qcow2"),
        virtualization_network_name="kc-test",
    )
    assert result.status == "blocked"
    assert "disabled" in result.error_message


def test_duplicate_create_never_resurrects_stopped_session(
    tmp_path,
    monkeypatch,
):
    _good_environment(monkeypatch)

    session_id = uuid4()

    create_job = _job(
        "gaming.session.create",
        session_id,
        gpu_uuid="GPU-A",
        minimum_vram_mb=8192,
    )

    created = execute_node_job(
        create_job,
        gaming_state_root=tmp_path,
        **COMMON,
    )

    assert created.status == "succeeded"

    stopped = execute_node_job(
        _job("gaming.session.stop", session_id),
        gaming_state_root=tmp_path,
        **COMMON,
    )

    assert stopped.status == "succeeded"
    assert stopped.result["status"] == "stopped"

    replay = execute_node_job(
        create_job,
        gaming_state_root=tmp_path,
        **COMMON,
    )

    assert replay.status == "succeeded"
    assert replay.result["idempotent"] is True
    assert replay.result["status"] == "stopped"
    assert "connection_info" not in replay.result

    state_file = (
        tmp_path
        / "sessions"
        / f"kc-gaming-{session_id}.json"
    )

    import json

    state = json.loads(state_file.read_text())

    assert state["status"] == "stopped"



def test_kg002_catalog_session_prepares_game_without_auto_launch(
    tmp_path,
    monkeypatch,
):
    _good_environment(monkeypatch)

    # This Linux unit test exercises the Windows-native commercial
    # session contract.  Production _interactive_session_context()
    # normalizes the broker's InteractiveSession object into this
    # verified dictionary before Y44E establishes its observation
    # boundary.
    monkeypatch.setattr(
        gaming_runtime,
        "_interactive_session_context",
        lambda: {
            "required": True,
            "validated": True,
            "session_id": 1,
            "execution_context": "interactive_user",
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
            "name": "Counter-Strike 2",
            "installed": True,
            "install_path": (
                r"C:\Steam\steamapps\common"
                r"\Counter-Strike Global Offensive"
            ),
        },
        launcher_executable=r"C:\Steam\steam.exe",
    )

    prepared_payloads = []

    def fake_prepare(payload):
        prepared_payloads.append(dict(payload))
        return prepared

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        fake_prepare,
    )

    # Y44E establishes the customer-workload observation baseline
    # before exposing stream readiness.  This unit test runs on
    # non-Windows CI and is testing catalog preparation/no-auto-launch,
    # not the Windows process-enumeration primitive.
    monkeypatch.setattr(
        gaming_runtime,
        "snapshot_game_processes",
        lambda **kwargs: [],
    )

    launches = []

    def forbidden_launch(*args, **kwargs):
        launches.append((args, kwargs))
        raise AssertionError(
            "commercial session START must not auto-launch game"
        )

    monkeypatch.setattr(
        gaming_runtime,
        "launch_prepared_game",
        forbidden_launch,
    )

    session_id = uuid4()

    result = execute_node_job(
        _job(
            "gaming.session.create",
            session_id,
            gpu_uuid="GPU-A",
            minimum_vram_mb=8192,
            game_slug="counter-strike-2",
            launcher="steam",
            launcher_app_id="730",
        ),
        gaming_state_root=tmp_path,
        **COMMON,
    )

    assert result.status == "succeeded"
    assert len(prepared_payloads) == 1
    assert launches == []

    assert result.result["game"]["app_id"] == "730"
    assert result.result["game_slug"] == "counter-strike-2"
    assert result.result["launcher_type"] == "steam"
    assert result.result["launcher_game_id"] == "730"
    assert "launch_info" not in result.result

    state_file = (
        tmp_path
        / "sessions"
        / f"kc-gaming-{session_id}.json"
    )

    import json

    saved = json.loads(
        state_file.read_text(encoding="utf-8")
    )

    assert saved["status"] == "running"
    assert saved["runtime_stage"] == "stream_ready"
    assert saved["game_slug"] == "counter-strike-2"
    assert saved["launcher_type"] == "steam"
    assert saved["launcher_game_id"] == "730"
    assert saved["game"]["app_id"] == "730"
    assert "launch_info" not in saved

    readiness = saved["stream_readiness"]
    assert readiness["verified"] is True
    assert readiness["workload_process_required"] is False
    assert readiness["launcher_pid"] is None

    ownership = saved["runtime_ownership"]
    ownership_proof = (
        runtime_ownership.inspect_runtime_ownership(
            ownership
        )
    )

    assert (
        ownership_proof["ownership_boundary_verified"]
        is True
    )
    assert ownership_proof["owned_process_count"] == 0
    assert ownership_proof["clean"] is True

def test_kg002_generic_session_remains_backward_compatible(
    tmp_path,
    monkeypatch,
):
    _good_environment(monkeypatch)

    monkeypatch.setattr(
        gaming_runtime,
        "prepare_game_launch",
        lambda payload: None,
    )

    session_id = uuid4()

    result = execute_node_job(
        _job(
            "gaming.session.create",
            session_id,
            gpu_uuid="GPU-A",
            minimum_vram_mb=8192,
        ),
        gaming_state_root=tmp_path,
        **COMMON,
    )

    assert result.status == "succeeded"
    assert "game" not in result.result
    assert "launch_info" not in result.result


def test_vdd_activation_module_is_agent_owned():
    from khan_agent import vdd_activation

    assert (
        vdd_activation.VDD_INSTANCE_ID
        == r"ROOT\DISPLAY\0000"
    )


def test_vdd_activation_contract_has_no_machine_reboot():
    from pathlib import Path
    import khan_agent.vdd_activation as module

    text = Path(module.__file__).read_text(
        encoding="utf-8"
    ).lower()

    assert "pnputil" in text
    assert "/restart-device" in text
    assert "reboot_required" in text
    assert "restart-computer" not in text
    assert "shutdown.exe" not in text
