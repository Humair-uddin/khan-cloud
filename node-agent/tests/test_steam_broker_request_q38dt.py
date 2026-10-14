import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = ROOT / "khan_agent" / "gaming_launchers.py"
BACKENDS = ROOT / "khan_agent" / "gaming_backends.py"


def _steam_adapter_launch():
    tree = ast.parse(LAUNCHERS.read_text(encoding="utf-8"))

    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "SteamLauncherAdapter"
        ):
            for child in node.body:
                if (
                    isinstance(child, ast.FunctionDef)
                    and child.name == "launch"
                ):
                    return child

    raise AssertionError("SteamLauncherAdapter.launch not found")


def test_q38dt_broker_request_does_not_claim_job_object():
    launch = _steam_adapter_launch()

    calls = [
        node
        for node in ast.walk(launch)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "launch_steam_app"
        )
    ]

    assert calls

    broker_calls = []

    for call in calls:
        keywords = {
            keyword.arg
            for keyword in call.keywords
            if keyword.arg is not None
        }

        if "expected_session_id" in keywords:
            broker_calls.append(call)

    assert broker_calls

    # At least one managed-session Steam request must deliberately omit
    # runtime_id.  That request is authority to ask the already-running
    # Steam broker to launch the game, not workload lifetime ownership.
    assert any(
        "runtime_id"
        not in {
            keyword.arg
            for keyword in call.keywords
            if keyword.arg is not None
        }
        for call in broker_calls
    )


def test_q38dt_brokered_game_still_requires_verified_process_ownership():
    source = LAUNCHERS.read_text(encoding="utf-8")

    assert "snapshot_game_processes(" in source
    assert "wait_for_new_game_processes(" in source
    assert "make_verified_process_ownership(" in source
    assert '"steam_brokered_verified_process"' in source
    assert '"launch_request_ownership"' in source


def test_q38dt_direct_runtime_launch_contract_remains_available():
    source = BACKENDS.read_text(encoding="utf-8")

    assert "if runtime_id:" in source
    assert "ownership_name=windows_job_name(" in source
