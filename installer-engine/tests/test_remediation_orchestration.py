import os
import sys
from pathlib import Path

import pytest

from kc_installer.engine import (
    RemediationExecutionError,
    execute_remediation_attempt,
)
from kc_installer.models import Manifest
from kc_installer.preflight import RemediationPolicyDecision
from kc_installer.state import InstallerState


def make_manifest(dependency_command: str) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-ORCHESTRATION",
                "name": "Remediation Orchestration Test",
                "version": "1.0.0",
            },
            "components": {},
            "preflight": {
                "dependencies": [
                    {
                        "name": "Test Dependency",
                        "command": dependency_command,
                        "classification": "remediable",
                    }
                ]
            },
        }
    )


def make_decision(
    command: list[str],
    *,
    eligible: bool = True,
    reason: str = "eligible",
) -> RemediationPolicyDecision:
    return RemediationPolicyDecision(
        dependency_name="Test Dependency",
        action_type="command",
        command=command,
        description="Test remediation.",
        eligible=eligible,
        reason=reason,
    )


def make_state(
    tmp_path: Path,
    decision: RemediationPolicyDecision,
) -> tuple[InstallerState, str]:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-ORCHESTRATION",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    state.record_remediation_plan(
        transaction_id,
        [
            {
                "dependency_name": decision.dependency_name,
                "action_type": decision.action_type,
                "command": list(decision.command),
                "description": decision.description,
                "eligible": decision.eligible,
                "policy_reason": decision.reason,
            }
        ],
    )

    return state, transaction_id


def test_orchestration_persists_success(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    dependency = "kc-orchestration-created-command"
    executable = bin_dir / dependency

    monkeypatch.setenv(
        "PATH",
        str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
    )

    script = (
        "from pathlib import Path; import os; "
        f"p=Path({str(executable)!r}); "
        "p.write_text('#!/bin/sh\\nexit 0\\n'); "
        "os.chmod(p, 0o755); "
        "print('remediation-success')"
    )

    decision = make_decision(
        [sys.executable, "-c", script]
    )

    manifest = make_manifest(dependency)
    state, transaction_id = make_state(tmp_path, decision)

    result = execute_remediation_attempt(
        state=state,
        transaction_id=transaction_id,
        position=0,
        decision=decision,
        manifest=manifest,
        cwd=tmp_path,
    )

    assert result.verified is True

    attempts = state.remediation_attempts(transaction_id)

    assert len(attempts) == 1
    assert attempts[0]["status"] == "success"
    assert attempts[0]["return_code"] == 0
    assert attempts[0]["timed_out"] is False
    assert attempts[0]["verified"] is True
    assert "remediation-success" in attempts[0]["stdout"]


def test_orchestration_persists_command_failure(
    tmp_path: Path,
) -> None:
    decision = make_decision(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "print('remediation-failed', file=sys.stderr); "
                "sys.exit(13)"
            ),
        ]
    )

    manifest = make_manifest("kc-command-still-missing")
    state, transaction_id = make_state(tmp_path, decision)

    with pytest.raises(Exception):
        execute_remediation_attempt(
            state=state,
            transaction_id=transaction_id,
            position=0,
            decision=decision,
            manifest=manifest,
            cwd=tmp_path,
        )

    attempts = state.remediation_attempts(transaction_id)

    assert len(attempts) == 1
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["return_code"] == 13
    assert attempts[0]["timed_out"] is False
    assert "remediation-failed" in attempts[0]["stderr"]
    assert attempts[0]["verified"] is False


def test_orchestration_persists_timeout(
    tmp_path: Path,
) -> None:
    decision = make_decision(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ]
    )

    manifest = make_manifest("kc-timeout-dependency")
    state, transaction_id = make_state(tmp_path, decision)

    with pytest.raises(Exception):
        execute_remediation_attempt(
            state=state,
            transaction_id=transaction_id,
            position=0,
            decision=decision,
            manifest=manifest,
            cwd=tmp_path,
            timeout_seconds=0.05,
        )

    attempts = state.remediation_attempts(transaction_id)

    assert len(attempts) == 1
    assert attempts[0]["status"] == "timeout"
    assert attempts[0]["return_code"] is None
    assert attempts[0]["timed_out"] is True
    assert attempts[0]["verified"] is False


def test_orchestration_persists_verification_failure(
    tmp_path: Path,
) -> None:
    decision = make_decision(
        [
            sys.executable,
            "-c",
            "print('ran-but-did-not-fix')",
        ]
    )

    manifest = make_manifest("kc-never-created")
    state, transaction_id = make_state(tmp_path, decision)

    with pytest.raises(
        RemediationExecutionError,
        match="still unavailable",
    ):
        execute_remediation_attempt(
            state=state,
            transaction_id=transaction_id,
            position=0,
            decision=decision,
            manifest=manifest,
            cwd=tmp_path,
        )

    attempts = state.remediation_attempts(transaction_id)

    assert len(attempts) == 1
    assert attempts[0]["status"] == "failed"
    assert attempts[0]["return_code"] == 0
    assert attempts[0]["timed_out"] is False
    assert attempts[0]["verified"] is False
    assert "ran-but-did-not-fix" in attempts[0]["stdout"]


def test_orchestration_records_ineligible_attempt_as_blocked(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "must-not-exist"

    decision = make_decision(
        [
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).touch()",
        ],
        eligible=False,
        reason="package trust has not been verified",
    )

    manifest = make_manifest("kc-blocked-dependency")
    state, transaction_id = make_state(tmp_path, decision)

    with pytest.raises(
        RemediationExecutionError,
        match="not eligible",
    ):
        execute_remediation_attempt(
            state=state,
            transaction_id=transaction_id,
            position=0,
            decision=decision,
            manifest=manifest,
            cwd=tmp_path,
        )

    assert not marker.exists()

    attempts = state.remediation_attempts(transaction_id)

    assert len(attempts) == 1
    assert attempts[0]["status"] == "blocked"
    assert attempts[0]["return_code"] is None
    assert attempts[0]["verified"] is False
