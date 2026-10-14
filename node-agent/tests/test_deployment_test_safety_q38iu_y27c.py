from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

from khan_agent import gaming_runtime
from khan_agent import runtime_ownership
from khan_agent import windows_interactive
from khan_agent import windows_presentation


pytestmark = pytest.mark.deployment_safe

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_SCRIPTS = (
    ROOT / "deploy" / "install-runtime.ps1",
    ROOT / "deploy" / "apply-runtime-update.ps1",
)


def _pytest_invocations(source: str) -> list[str]:
    return [
        line.strip()
        for line in source.splitlines()
        if re.search(r"\bpytest\b", line)
        and not line.lstrip().startswith("#")
    ]


@pytest.mark.parametrize("script", DEPLOYMENT_SCRIPTS)
def test_deployment_scripts_use_only_positive_safe_allowlist(
    script: Path,
):
    source = script.read_text(encoding="utf-8-sig")
    invocations = _pytest_invocations(source)

    assert invocations == [
        '& $Python -m pytest -q -m "deployment_safe"'
    ]
    assert '-m "not source_tree_only"' not in source
    assert '-m "not deployment_safe"' not in source


def test_deployment_safe_marker_is_registered():
    pyproject = (ROOT / "pyproject.toml").read_text(
        encoding="utf-8"
    )

    assert (
        "deployment_safe: explicitly audited as "
        "side-effect-free on an installed production Windows host"
        in pyproject
    )


def test_critical_runtime_modules_import_from_candidate_tree():
    module_names = (
        "khan_agent.gaming_runtime",
        "khan_agent.gaming_launchers",
        "khan_agent.windows_presentation",
        "khan_agent.windows_verified_process",
        "khan_agent.runtime_ownership",
        "khan_agent.windows_interactive",
        "khan_agent.windows_session_broker",
    )

    for module_name in module_names:
        module = importlib.import_module(module_name)
        module_path = Path(module.__file__).resolve()
        assert module_path.is_relative_to(ROOT)


def test_required_runtime_dependencies_import():
    required = [
        "httpx",
        "psutil",
        "pydantic",
        "yaml",
    ]

    if sys.platform == "win32":
        required.extend(
            (
                "servicemanager",
                "win32event",
                "win32service",
                "win32serviceutil",
                "win32ts",
            )
        )

    for module_name in required:
        importlib.import_module(module_name)


def test_runtime_ownership_proof_is_json_round_trip_safe():
    proof = runtime_ownership.no_process_ownership()
    restored = json.loads(json.dumps(proof))

    assert restored == proof

    inspected = (
        runtime_ownership.inspect_runtime_ownership(
            restored
        )
    )

    assert inspected["ownership_boundary_verified"] is True
    assert inspected["owned_process_count"] == 0
    assert inspected["owned_processes"] == []
    assert inspected["clean"] is True


def test_deployment_safe_tripwire_covers_live_mutation_paths(
    deployment_safe_runtime_guard,
):
    expected = {
        "khan_agent.gaming_runtime._establish_presentation_contract",
        "khan_agent.gaming_runtime._apply_session_display_policy",
        "khan_agent.gaming_runtime.prepare_game_launch",
        "khan_agent.gaming_runtime.launch_prepared_game",
        "khan_agent.gaming_runtime.activate_vdd_policy",
        "khan_agent.gaming_runtime._cleanup_failed_launch",
        "khan_agent.gaming_launchers.prepare_game_launch",
        "khan_agent.gaming_launchers.launch_prepared_game",
        "khan_agent.windows_presentation.establish_vdd_presentation_contract",
        "khan_agent.windows_presentation.ensure_game_on_vdd",
        "khan_agent.windows_interactive.launch_in_active_session",
        "khan_agent.vdd_activation.restart_vdd_device",
        "khan_agent.vdd_activation.activate_vdd_policy",
        "khan_agent.vdd_runtime_policy.apply_display_policy",
        "khan_agent.vdd_runtime_policy.restore_last_known_good",
        "khan_agent.runtime_ownership.terminate_runtime_ownership",
    }

    assert deployment_safe_runtime_guard == expected
    assert getattr(
        gaming_runtime._establish_presentation_contract,
        "_khan_deployment_safe_guard",
        False,
    )
    assert getattr(
        windows_presentation.ensure_game_on_vdd,
        "_khan_deployment_safe_guard",
        False,
    )
    assert getattr(
        windows_interactive.launch_in_active_session,
        "_khan_deployment_safe_guard",
        False,
    )
