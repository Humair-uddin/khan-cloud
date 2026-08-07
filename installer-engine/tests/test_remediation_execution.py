import os
import sys
from pathlib import Path

import pytest

from kc_installer.engine import (
    RemediationExecutionError,
    execute_remediation,
)
from kc_installer.models import Manifest
from kc_installer.preflight import RemediationPolicyDecision


def make_manifest(
    dependency_command: str,
) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-REMEDIATION-EXEC",
                "name": "Remediation Execution Test",
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
    action_type: str = "command",
    reason: str = "eligible",
) -> RemediationPolicyDecision:
    return RemediationPolicyDecision(
        dependency_name="Test Dependency",
        action_type=action_type,
        command=command,
        description="Test remediation.",
        eligible=eligible,
        reason=reason,
    )


def test_remediation_refuses_ineligible_action(
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

    manifest = make_manifest("kc-test-dependency")

    with pytest.raises(
        RemediationExecutionError,
        match="not eligible",
    ):
        execute_remediation(
            decision,
            manifest,
            cwd=tmp_path,
        )

    assert not marker.exists()


def test_remediation_refuses_unsupported_action_type(
    tmp_path: Path,
) -> None:
    decision = make_decision(
        ["echo", "should-not-run"],
        action_type="unsupported",
    )

    manifest = make_manifest("kc-test-dependency")

    with pytest.raises(
        RemediationExecutionError,
        match="Unsupported remediation action type",
    ):
        execute_remediation(
            decision,
            manifest,
            cwd=tmp_path,
        )


def test_remediation_requires_matching_dependency(
    tmp_path: Path,
) -> None:
    decision = RemediationPolicyDecision(
        dependency_name="Unknown Dependency",
        action_type="command",
        command=["echo", "test"],
        description="Test.",
        eligible=True,
        reason="eligible",
    )

    manifest = make_manifest("kc-test-dependency")

    with pytest.raises(
        RemediationExecutionError,
        match="Dependency not found in manifest",
    ):
        execute_remediation(
            decision,
            manifest,
            cwd=tmp_path,
        )


def test_successful_command_must_make_dependency_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    dependency = "kc-remediation-created-command"
    executable = bin_dir / dependency

    monkeypatch.setenv(
        "PATH",
        str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
    )

    script = (
        "from pathlib import Path; import os; "
        f"p=Path({str(executable)!r}); "
        "p.write_text('#!/bin/sh\\nexit 0\\n'); "
        "os.chmod(p, 0o755)"
    )

    decision = make_decision(
        [
            sys.executable,
            "-c",
            script,
        ]
    )

    manifest = make_manifest(dependency)

    result = execute_remediation(
        decision,
        manifest,
        cwd=tmp_path,
    )

    assert result.dependency_name == "Test Dependency"
    assert result.dependency_command == dependency
    assert result.verified is True
    assert result.command_result.returncode == 0
    assert executable.exists()


def test_command_success_without_dependency_is_failure(
    tmp_path: Path,
) -> None:
    dependency = "kc-dependency-that-stays-missing"

    decision = make_decision(
        [
            sys.executable,
            "-c",
            "print('command succeeded but fixed nothing')",
        ]
    )

    manifest = make_manifest(dependency)

    with pytest.raises(
        RemediationExecutionError,
        match="still unavailable",
    ) as exc_info:
        execute_remediation(
            decision,
            manifest,
            cwd=tmp_path,
        )

    assert exc_info.value.command_result is not None
    assert exc_info.value.command_result.returncode == 0
