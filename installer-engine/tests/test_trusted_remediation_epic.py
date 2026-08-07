import base64
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kc_installer.engine import install, execute_command
from kc_installer.paths import InstallerPaths
from kc_installer.state import InstallerState
from kc_installer.trust import package_digest


def make_paths(root: Path) -> InstallerPaths:
    return InstallerPaths(
        source_root=root / "source", platform_root=root,
        runtime_root=root / "runtime" / "installer",
        state_root=root / "state" / "installer",
        backup_root=root / "backups" / "feature-packs",
        package_root=root / "packages",
    )


def sign(package: Path, paths: InstallerPaths) -> None:
    paths.ensure_directories()
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    (paths.trust_store_dir / "test.json").write_text(json.dumps({
        "signer_id": "test-signer",
        "public_key": base64.b64encode(public).decode(),
    }))
    digest = package_digest(package)
    signature = private.sign(digest.encode("ascii"))
    (package / "signature.json").write_text(json.dumps({
        "signer_id": "test-signer",
        "algorithm": "ed25519",
        "signature": base64.b64encode(signature).decode(),
    }))


def test_signed_package_automatically_remediates(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path / "cloud")
    package = tmp_path / "package"; package.mkdir()
    target = tmp_path / "target"; target.mkdir()
    bindir = tmp_path / "bin"; bindir.mkdir()
    dep = "kc-epic-test-dependency"
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    command = [sys.executable, "-c", (
        "from pathlib import Path; import os; "
        f"p=Path({str(bindir / dep)!r}); "
        "p.write_text('#!/bin/sh\\nexit 0\\n'); os.chmod(p, 0o755)"
    )]
    import yaml
    (package / "manifest.yaml").write_text(yaml.safe_dump({
        "feature_pack": {"id":"FP-EPIC","name":"Epic","version":"1.0.0"},
        "components": {},
        "operations": {"require_clean_git": False, "allow_dependency_install": True,
                       "run_health_checks": False},
        "preflight": {"dependencies": [{"name":"Epic Dependency", "command":dep,
            "classification":"remediable", "remediation":{"type":"command",
            "command":command, "description":"install test dependency"}}]},
    }, sort_keys=False))
    sign(package, paths)
    report = install(package, target, dry_run=False, paths=paths)
    assert report.exists()
    state = InstallerState(paths.database_path)
    tx = state.installations(1)[0]
    assert tx["package_trusted"] == 1
    assert tx["signer_id"] == "test-signer"
    assert state.remediation_plan(tx["transaction_id"])[0]["eligible"] is True
    attempts = state.remediation_attempts(tx["transaction_id"])
    assert len(attempts) == 1 and attempts[0]["status"] == "success"
    assert attempts[0]["verified"] is True


def test_unsigned_package_never_auto_remediates(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path / "cloud")
    package = tmp_path / "package"; package.mkdir()
    target = tmp_path / "target"; target.mkdir()
    marker = tmp_path / "must-not-run"
    import yaml
    (package / "manifest.yaml").write_text(yaml.safe_dump({
        "feature_pack":{"id":"FP-U","name":"Unsigned","version":"1"}, "components":{},
        "operations":{"require_clean_git":False,"allow_dependency_install":True,"run_health_checks":False},
        "preflight":{"dependencies":[{"name":"Missing","command":"kc-never-there",
          "classification":"remediable","remediation":{"type":"command","command":[sys.executable,"-c",f"from pathlib import Path; Path({str(marker)!r}).touch()"]}}]},
    }, sort_keys=False))
    install(package, target, dry_run=False, paths=paths)
    assert not marker.exists()
    state=InstallerState(paths.database_path); tx=state.installations(1)[0]
    assert tx["package_trusted"] == 0
    assert state.remediation_attempts(tx["transaction_id"]) == []


def test_command_output_is_redacted_and_bounded(tmp_path: Path) -> None:
    result = execute_command([sys.executable, "-c", "print('token=supersecret'); print('x'*70000)"], cwd=tmp_path)
    assert "supersecret" not in result.stdout
    assert "[REDACTED]" in result.stdout
    assert "[TRUNCATED" in result.stdout
    assert len(result.stdout) < 66000


def test_running_attempt_can_be_marked_interrupted(tmp_path: Path) -> None:
    state=InstallerState(tmp_path/'installer.db')
    tx=state.begin(feature_pack_id='FP', feature_pack_version='1', package_path=tmp_path/'p', target_path=tmp_path/'t', backup_path=tmp_path/'b', dry_run=False)
    state.record_remediation_plan(tx,[{"dependency_name":"D","action_type":"command","command":["true"],"eligible":True,"policy_reason":"eligible"}])
    state.begin_remediation_attempt(tx,0)
    assert state.interrupt_running_remediation_attempts(tx) == 1
    attempt=state.remediation_attempts(tx)[0]
    assert attempt['status']=='interrupted' and attempt['verified'] is False


def test_shell_interpreter_remediation_is_blocked_even_when_trusted(tmp_path: Path) -> None:
    from kc_installer.models import Manifest
    from kc_installer.preflight import evaluate_remediation_policy
    manifest = Manifest.model_validate({
        "feature_pack":{"id":"FP-SHELL","name":"Shell","version":"1"},
        "components":{}, "operations":{"allow_dependency_install":True},
        "preflight":{"dependencies":[{"name":"D","command":"kc-no-shell-dep","classification":"remediable",
          "remediation":{"type":"command","command":["bash","-c","echo unsafe"]}}]},
    })
    decision=evaluate_remediation_policy(manifest,dry_run=False,trusted_package=True)[0]
    assert decision.eligible is False
    assert "shell interpreters" in decision.reason
