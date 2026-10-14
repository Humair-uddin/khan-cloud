import json
from pathlib import Path

from khan_agent import gaming_runtime as gr


def test_y44j_periodic_reconcile_scans_canonical_sessions_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "gaming"
    paths = gr.GamingRuntimePaths(root)

    runtime_id = (
        "kc-gaming-"
        "59f0874e-69c6-4e59-bb46-1bb18e104375"
    )
    state_file = paths.session_file(runtime_id)

    process = {
        "pid": 18144,
        "creation_time_100ns": 134349286579592844,
        "executable": (
            r"C:\Program Files (x86)\Steam\steamapps\common"
            r"\Counter-Strike Global Offensive"
            r"\game\bin\win64\cs2.exe"
        ),
        "session_id": 1,
    }

    authority = {
        "schema_version": 1,
        "authority_type": "customer_game_workload_observation",
        "runtime_id": runtime_id,
        "install_root": (
            r"C:\Program Files (x86)\Steam\steamapps\common"
            r"\Counter-Strike Global Offensive"
        ),
        "interactive_session_id": 1,
        "launcher_type": "steam",
        "launcher_game_id": "730",
        "baseline": [],
    }

    state = {
        "schema_version": 2,
        "session_id": "59f0874e-69c6-4e59-bb46-1bb18e104375",
        "runtime_id": runtime_id,
        "status": "running",
        "runtime_stage": "stream_ready",
        "runtime_ownership": gr.no_process_ownership(),
        "workload_observation": {
            "schema_version": 1,
            "generation": 1,
            "state": "armed",
            "authority": authority,
            "last_observed_processes": [],
        },
    }

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(state),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        gr,
        "discover_customer_workload_processes",
        lambda observed_authority: [process],
    )

    monkeypatch.setattr(
        gr,
        "adopt_customer_workload",
        lambda observed_authority, processes: {
            "schema_version": 2,
            "ownership_type": "windows_verified_process",
            "ownership_boundary_established": True,
            "runtime_id": runtime_id,
            "processes": list(processes),
        },
    )

    outcomes = gr.reconcile_customer_workloads(root)

    assert len(outcomes) == 1
    assert outcomes[0]["changed"] is True
    assert outcomes[0]["state"] == "running"
    assert outcomes[0]["owned_process_count"] == 1

    persisted = json.loads(
        state_file.read_text(encoding="utf-8")
    )

    assert (
        persisted["runtime_ownership"]["ownership_type"]
        == "windows_verified_process"
    )
    assert (
        persisted["runtime_ownership"]["processes"][0]["pid"]
        == 18144
    )
    assert (
        persisted["workload_observation"]["state"]
        == "running"
    )
    assert (
        persisted["workload_observation"]
        ["last_observed_processes"][0]["pid"]
        == 18144
    )


def test_y44j_periodic_reconcile_does_not_scan_legacy_root_layout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "gaming"
    root.mkdir(parents=True)

    legacy_file = root / "session-test.json"
    legacy_file.write_text(
        json.dumps(
            {
                "status": "running",
                "runtime_stage": "stream_ready",
            }
        ),
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
