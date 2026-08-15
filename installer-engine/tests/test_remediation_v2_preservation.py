from pathlib import Path
import pytest

from kc_installer.engine import (
    RemediationExecutionError,
    execute_remediation,
)
from kc_installer.models import Manifest
from kc_installer.preflight import (
    build_remediation_plan,
    evaluate_remediation_policy,
)


def manifest_for(
    *,
    dependency_command: str,
    remediation_command: list[str],
    allow_dependency_install: bool = True,
) -> Manifest:
    return Manifest.model_validate(
        {
            "feature_pack": {
                "id": "FP-REMEDIATION-V2",
                "name": "Remediation V2",
                "version": "1.0.0",
            },
            "components": {},
            "operations": {
                "allow_dependency_install": allow_dependency_install,
            },
            "preflight": {
                "dependencies": [
                    {
                        "name": "Test Dependency",
                        "command": dependency_command,
                        "classification": "remediable",
                        "remediation": {
                            "type": "command",
                            "command": remediation_command,
                            "description": "approved test remediation",
                        },
                    }
                ]
            },
        }
    )


def test_available_dependency_has_no_remediation_plan(
    monkeypatch,
):
    manifest = manifest_for(
        dependency_command="kc-remediation-v2-present",
        remediation_command=["never-run"],
    )

    monkeypatch.setattr(
        "kc_installer.preflight.shutil.which",
        lambda command: "/already/available/" + command,
    )

    assert build_remediation_plan(manifest) == []


def test_available_dependency_has_no_policy_decision(
    monkeypatch,
):
    manifest = manifest_for(
        dependency_command="kc-remediation-v2-present",
        remediation_command=["never-run"],
    )

    monkeypatch.setattr(
        "kc_installer.preflight.shutil.which",
        lambda command: "/already/available/" + command,
    )

    assert evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    ) == []


def test_execution_refuses_stale_plan_when_dependency_became_available(
    monkeypatch,
    tmp_path: Path,
):
    dependency = "kc-remediation-v2-late-dependency"

    manifest = manifest_for(
        dependency_command=dependency,
        remediation_command=["approved-installer"],
    )

    decision = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    )[0]

    # Planning saw the dependency as missing. Before execution,
    # another process makes it operational.
    monkeypatch.setattr(
        "kc_installer.engine.shutil.which",
        lambda command: "/already/working/" + command,
        raising=False,
    )

    executed = []

    def forbidden_execute(*args, **kwargs):
        executed.append(True)
        raise AssertionError(
            "working dependency must never be remediated"
        )

    monkeypatch.setattr(
        "kc_installer.engine.execute_command",
        forbidden_execute,
    )

    with pytest.raises(
        RemediationExecutionError,
        match="already available",
    ):
        execute_remediation(
            decision,
            manifest,
            cwd=tmp_path,
        )

    assert executed == []


def test_missing_dependency_executes_then_is_redetected(
    monkeypatch,
    tmp_path: Path,
):
    dependency = "kc-remediation-v2-missing"
    installed = False

    manifest = manifest_for(
        dependency_command=dependency,
        remediation_command=["approved-installer"],
    )

    decision = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    )[0]

    def fake_which(command):
        if command != dependency:
            return None
        return "/installed/" + command if installed else None

    monkeypatch.setattr(
        "kc_installer.engine.shutil.which",
        fake_which,
        raising=False,
    )

    from kc_installer.engine import CommandExecutionResult

    def fake_execute(command, *, cwd, timeout_seconds):
        nonlocal installed
        installed = True
        return CommandExecutionResult(
            command=list(command),
            returncode=0,
            stdout="installed",
            stderr="",
        )

    monkeypatch.setattr(
        "kc_installer.engine.execute_command",
        fake_execute,
    )

    result = execute_remediation(
        decision,
        manifest,
        cwd=tmp_path,
    )

    assert installed is True
    assert result.verified is True


def test_successful_command_without_dependency_fails_closed(
    monkeypatch,
    tmp_path: Path,
):
    dependency = "kc-remediation-v2-never-appears"

    manifest = manifest_for(
        dependency_command=dependency,
        remediation_command=["approved-installer"],
    )

    decision = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    )[0]

    monkeypatch.setattr(
        "kc_installer.engine.shutil.which",
        lambda command: None,
        raising=False,
    )

    from kc_installer.engine import CommandExecutionResult

    monkeypatch.setattr(
        "kc_installer.engine.execute_command",
        lambda command, *, cwd, timeout_seconds:
            CommandExecutionResult(
                command=list(command),
                returncode=0,
                stdout="installer returned success",
                stderr="",
            ),
    )

    with pytest.raises(
        RemediationExecutionError,
        match="still unavailable",
    ):
        execute_remediation(
            decision,
            manifest,
            cwd=tmp_path,
        )


def test_untrusted_package_cannot_remediate_missing_dependency():
    manifest = manifest_for(
        dependency_command="kc-remediation-v2-untrusted",
        remediation_command=["approved-installer"],
    )

    decision = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=False,
    )[0]

    assert decision.eligible is False
    assert "trust" in decision.reason


def test_dry_run_never_authorizes_mutation():
    manifest = manifest_for(
        dependency_command="kc-remediation-v2-dry-run",
        remediation_command=["approved-installer"],
    )

    decision = evaluate_remediation_policy(
        manifest,
        dry_run=True,
        trusted_package=True,
    )[0]

    assert decision.eligible is False
    assert "dry-run" in decision.reason


def test_dependency_install_permission_is_required():
    manifest = manifest_for(
        dependency_command="kc-remediation-v2-disabled",
        remediation_command=["approved-installer"],
        allow_dependency_install=False,
    )

    decision = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    )[0]

    assert decision.eligible is False
    assert "not permitted" in decision.reason


def test_default_remediation_contract_is_missing_only_and_verified():
    manifest = manifest_for(
        dependency_command="kc-remediation-v2-contract",
        remediation_command=["approved-installer"],
    )

    remediation = manifest.preflight.dependencies[0].remediation

    assert remediation is not None
    assert remediation.mutation_policy == "missing_only"
    assert remediation.verify_after_execution is True

    decision = evaluate_remediation_policy(
        manifest,
        dry_run=False,
        trusted_package=True,
    )[0]

    assert decision.mutation_policy == "missing_only"
    assert decision.verify_after_execution is True
