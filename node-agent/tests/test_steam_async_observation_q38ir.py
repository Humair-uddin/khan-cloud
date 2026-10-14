from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = ROOT / "khan_agent" / "gaming_launchers.py"
VERIFIER = (
    ROOT / "khan_agent" / "windows_verified_process.py"
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_steam_policy_is_explicit_and_bounded():
    tree = ast.parse(_source(LAUNCHERS))
    value = None

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue

        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id
                == "_STEAM_BROKER_PROCESS_TIMEOUT_SECONDS"
            ):
                value = ast.literal_eval(node.value)

    assert value == 120.0
    assert 76.0 < value < 300.0


def test_generic_default_remains_45_seconds():
    assert (
        "timeout_seconds: float = 45.0"
        in _source(VERIFIER)
    )


def test_steam_call_passes_launcher_specific_timeout():
    source = _source(LAUNCHERS)

    start = source.index(
        "processes = wait_for_new_game_processes("
    )
    end = source.index(
        "runtime_ownership = (",
        start,
    )
    call = source[start:end]

    assert "baseline=baseline" in call
    assert "timeout_seconds=(" in call
    assert (
        "_STEAM_BROKER_PROCESS_TIMEOUT_SECONDS"
        in call
    )


def test_verifier_still_excludes_baseline():
    source = _source(VERIFIER)

    assert "baseline_keys = {" in source
    assert "not in baseline_keys" in source


def test_verifier_still_requires_session_and_root():
    source = _source(VERIFIER)

    assert 'identity["session_id"]' in source
    assert "expected_session_id" in source
    assert "path_is_within_install_root(" in source


def test_verifier_wait_remains_bounded():
    source = _source(VERIFIER)

    assert "deadline = time.monotonic() + max(" in source
    assert "while time.monotonic() < deadline:" in source


def test_wait_accepts_delayed_new_identity(monkeypatch):
    import khan_agent.windows_verified_process as wvp

    baseline = [
        {
            "pid": 100,
            "creation_time_100ns": 1000,
            "executable": r"C:\Games\CS2\old.exe",
            "session_id": 1,
        }
    ]

    new_identity = {
        "pid": 200,
        "creation_time_100ns": 2000,
        "executable": r"C:\Games\CS2\cs2.exe",
        "session_id": 1,
    }

    snapshots = [
        list(baseline),
        list(baseline),
        list(baseline) + [new_identity],
        list(baseline) + [new_identity],
    ]

    def fake_snapshot(**kwargs):
        if len(snapshots) > 1:
            return snapshots.pop(0)
        return snapshots[0]

    clock = {"value": 0.0}

    def fake_monotonic():
        clock["value"] += 0.25
        return clock["value"]

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        fake_snapshot,
    )
    monkeypatch.setattr(
        wvp.time,
        "monotonic",
        fake_monotonic,
    )
    monkeypatch.setattr(
        wvp.time,
        "sleep",
        lambda _: None,
    )

    result = wvp.wait_for_new_game_processes(
        install_root=r"C:\Games\CS2",
        expected_session_id=1,
        baseline=baseline,
        timeout_seconds=10.0,
        settle_seconds=0.0,
    )

    assert result == [new_identity]


def test_wait_rejects_baseline_only_until_timeout(
    monkeypatch,
):
    import khan_agent.windows_verified_process as wvp

    baseline = [
        {
            "pid": 100,
            "creation_time_100ns": 1000,
            "executable": r"C:\Games\CS2\cs2.exe",
            "session_id": 1,
        }
    ]

    monkeypatch.setattr(
        wvp,
        "snapshot_game_processes",
        lambda **kwargs: list(baseline),
    )

    clock = {"value": 0.0}

    def fake_monotonic():
        clock["value"] += 1.0
        return clock["value"]

    monkeypatch.setattr(
        wvp.time,
        "monotonic",
        fake_monotonic,
    )
    monkeypatch.setattr(
        wvp.time,
        "sleep",
        lambda _: None,
    )

    with pytest.raises(
        wvp.WindowsVerifiedProcessError,
        match="did not produce a new verified game process",
    ):
        wvp.wait_for_new_game_processes(
            install_root=r"C:\Games\CS2",
            expected_session_id=1,
            baseline=baseline,
            timeout_seconds=5.0,
            settle_seconds=0.0,
        )


def test_y9_trace_has_utc_correlation_and_monotonic_deltas(caplog):
    from khan_agent.launch_diagnostics import LaunchTrace
    caplog.set_level("INFO", logger="khan_agent.launch_diagnostics")
    trace = LaunchTrace("attempt-7", "runtime-9")
    trace.emit("launcher_request_begin")
    trace.emit("launcher_request_returned", request_pid=123)
    assert len(caplog.records) == 2
    for record in caplog.records:
        assert "attempt-7" in record.message
        assert "runtime-9" in record.message
        assert "utc" in record.message
        assert "elapsed_ms" in record.message
        assert "delta_ms" in record.message
    assert "request_pid" in caplog.records[1].message


def test_y9_observation_records_first_addition_replacement_and_settle(
    monkeypatch, caplog,
):
    import khan_agent.windows_verified_process as wvp
    caplog.set_level("INFO", logger="khan_agent.launch_diagnostics")
    def ident(pid, creation):
        return {
            "pid": pid,
            "creation_time_100ns": creation,
            "executable": r"C:\Games\CS2\cs2.exe",
            "session_id": 1,
        }
    first = ident(200, 2000)
    extra = ident(201, 2001)
    replacement = ident(200, 3000)
    snapshots = [
        [], [first], [first, extra], [replacement, extra],
    ]
    monkeypatch.setattr(
        wvp, "snapshot_game_processes",
        lambda **_kwargs: snapshots.pop(0) if len(snapshots) > 1 else snapshots[0],
    )
    monkeypatch.setattr(wvp.time, "sleep", lambda _seconds: None)
    result = wvp.wait_for_new_game_processes(
        install_root=r"C:\Games\CS2",
        expected_session_id=1,
        baseline=[],
        timeout_seconds=5,
        settle_seconds=0.3,
        attempt_id="attempt-late",
    )
    assert result == [replacement, extra]
    records = "\n".join(r.message for r in caplog.records)
    assert "observation_begin" in records
    assert "first_candidate" in records
    assert records.count("additional_or_replacement_candidate") >= 2
    assert "observation_settled" in records
    assert "attempt-late" in records
    assert "creation_time_100ns" in records
    assert "command_line" not in records
