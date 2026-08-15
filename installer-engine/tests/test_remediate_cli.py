import json
import os
import sys
import base64
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from kc_installer.trust import package_digest

from kc_installer.cli import main
from kc_installer.paths import InstallerPaths
from kc_installer.state import InstallerState


def make_paths(root: Path) -> InstallerPaths:
    return InstallerPaths(
        source_root=root / "source",
        platform_root=root,
        runtime_root=root / "runtime" / "installer",
        state_root=root / "state" / "installer",
        backup_root=root / "backups" / "feature-packs",
        package_root=root / "packages",
    )


def create_transaction(
    tmp_path: Path,
    *,
    remediation_command: list[str],
    dependency_command: str,
    eligible: bool,
    policy_reason: str,
) -> tuple[InstallerPaths, InstallerState, str, Path]:
    paths = make_paths(tmp_path / "khan-cloud")
    paths.ensure_directories()

    package = tmp_path / "package"
    package.mkdir()

    target = tmp_path / "target"
    target.mkdir()

    import yaml

    manifest = {
        "feature_pack": {
            "id": "FP-MANUAL-REMEDIATE",
            "name": "Manual Remediation Test",
            "version": "1.0.0",
        },
        "components": {},
        "operations": {
            "allow_dependency_install": True,
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
                        "description": "Test remediation.",
                    },
                }
            ]
        },
    }

    (package / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False)
    )

    state = InstallerState(paths.database_path)

    trust = None
    if eligible:
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
        from kc_installer.trust import verify_package_signature
        trust = verify_package_signature(package, paths.trust_store_dir)

    transaction_id = state.begin(
        feature_pack_id="FP-MANUAL-REMEDIATE",
        feature_pack_version="1.0.0",
        package_path=package,
        target_path=target,
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    if trust is not None:
        state.record_package_trust(
            transaction_id, trusted=trust.trusted, signer_id=trust.signer_id,
            package_digest=trust.package_digest, trust_reason=trust.reason,
        )

    state.record_remediation_plan(
        transaction_id,
        [
            {
                "dependency_name": "Test Dependency",
                "action_type": "command",
                "command": remediation_command,
                "description": "Test remediation.",
                "eligible": eligible,
                "policy_reason": policy_reason,
            }
        ],
    )

    return paths, state, transaction_id, target


def run_cli(
    monkeypatch,
    paths: InstallerPaths,
    transaction_id: str,
    *,
    position: int = 0,
    timeout_seconds: float | None = None,
) -> None:
    monkeypatch.setattr(
        InstallerPaths,
        "from_environment",
        classmethod(lambda cls: paths),
    )

    argv = [
        "kc-installer",
        "remediate",
        transaction_id,
        str(position),
    ]

    if timeout_seconds is not None:
        argv.extend(
            [
                "--timeout-seconds",
                str(timeout_seconds),
            ]
        )

    monkeypatch.setattr(sys, "argv", argv)

    main()


def test_remediate_cli_refuses_blocked_action(
    tmp_path: Path,
    monkeypatch,
) -> None:
    marker = tmp_path / "must-not-exist"

    command = [
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(marker)!r}).touch()",
    ]

    paths, state, transaction_id, _ = create_transaction(
        tmp_path,
        remediation_command=command,
        dependency_command="kc-blocked-dependency",
        eligible=False,
        policy_reason="package trust has not been verified",
    )

    with pytest.raises(
        SystemExit,
        match="Remediation blocked",
    ):
        run_cli(
            monkeypatch,
            paths,
            transaction_id,
        )

    assert not marker.exists()
    assert state.remediation_attempts(transaction_id) == []


def test_remediate_cli_executes_and_audits_eligible_action(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    dependency = "kc-manual-remediation-command"
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
        "print('manual-remediation-ok')"
    )

    command = [
        sys.executable,
        "-c",
        script,
    ]

    paths, state, transaction_id, _ = create_transaction(
        tmp_path,
        remediation_command=command,
        dependency_command=dependency,
        eligible=True,
        policy_reason="eligible",
    )

    run_cli(
        monkeypatch,
        paths,
        transaction_id,
    )

    output = json.loads(capsys.readouterr().out)

    assert output["transaction_id"] == transaction_id
    assert output["position"] == 0
    assert output["dependency_name"] == "Test Dependency"
    assert output["status"] == "success"
    assert output["verified"] is True

    attempt = output["attempt"]

    assert attempt["attempt_number"] == 1
    assert attempt["status"] == "success"
    assert attempt["return_code"] == 0
    assert attempt["verified"] is True
    assert "manual-remediation-ok" in attempt["stdout"]

    persisted = state.remediation_attempts(transaction_id)

    assert len(persisted) == 1
    assert persisted[0]["status"] == "success"


def test_remediate_cli_rejects_manifest_tampering(
    tmp_path: Path,
    monkeypatch,
) -> None:
    safe_command = [
        sys.executable,
        "-c",
        "print('safe-command')",
    ]

    paths, state, transaction_id, _ = create_transaction(
        tmp_path,
        remediation_command=safe_command,
        dependency_command="kc-tamper-dependency",
        eligible=True,
        policy_reason="eligible",
    )

    installation = state.installation(transaction_id)
    assert installation is not None

    package = Path(installation["package_path"])
    manifest_path = package / "manifest.yaml"

    import yaml

    raw = yaml.safe_load(manifest_path.read_text())

    marker = tmp_path / "tampered-command-ran"

    raw["preflight"]["dependencies"][0]["remediation"]["command"] = [
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(marker)!r}).touch()",
    ]

    manifest_path.write_text(
        yaml.safe_dump(raw, sort_keys=False)
    )

    with pytest.raises(
        SystemExit,
        match="trust no longer matches|manifest.*no longer match",
    ):
        run_cli(
            monkeypatch,
            paths,
            transaction_id,
        )

    assert not marker.exists()
    assert state.remediation_attempts(transaction_id) == []


def test_remediate_cli_preserves_retry_history(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """
    Remediation V2 preservation contract:

    First execution may install a missing dependency.

    Once that dependency is operational, a later retry must NOT execute
    the mutation again. The refused retry must still be persisted in the
    audit history so operators can see exactly what happened.
    """

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    dependency = "kc-retry-dependency"
    executable = bin_dir / dependency
    execution_counter = tmp_path / "execution-count.txt"

    monkeypatch.setenv(
        "PATH",
        str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
    )

    script = (
        "from pathlib import Path; import os; "
        f"p=Path({str(executable)!r}); "
        f"counter=Path({str(execution_counter)!r}); "
        "count=int(counter.read_text()) if counter.exists() else 0; "
        "counter.write_text(str(count + 1)); "
        "p.write_text('#!/bin/sh\\nexit 0\\n'); "
        "os.chmod(p, 0o755)"
    )

    command = [
        sys.executable,
        "-c",
        script,
    ]

    paths, state, transaction_id, _ = create_transaction(
        tmp_path,
        remediation_command=command,
        dependency_command=dependency,
        eligible=True,
        policy_reason="eligible",
    )

    # --------------------------------------------------------
    # First attempt: dependency is absent, so remediation runs.
    # --------------------------------------------------------

    run_cli(monkeypatch, paths, transaction_id)

    first_output = capsys.readouterr().out

    assert '"verified": true' in first_output.lower()
    assert executable.exists()
    assert execution_counter.read_text() == "1"

    first_attempts = [
        item
        for item in state.remediation_attempts(transaction_id)
        if item["position"] == 0
    ]

    assert len(first_attempts) == 1
    assert first_attempts[0]["attempt_number"] == 1
    assert first_attempts[0]["status"] == "success"
    assert first_attempts[0]["verified"] == 1

    # --------------------------------------------------------
    # Second attempt:
    #
    # The dependency is now operational. Preservation policy
    # must refuse another mutation instead of reinstalling,
    # upgrading, replacing, or otherwise touching it.
    # --------------------------------------------------------

    with pytest.raises(SystemExit) as exc_info:
        run_cli(monkeypatch, paths, transaction_id)

    assert exc_info.value.code == 1

    second_output = capsys.readouterr().out.lower()

    assert '"status": "blocked"' in second_output
    assert '"verified": false' in second_output
    assert "already available" in second_output
    assert "preservation policy" in second_output

    # Critical invariant: remediation command executed only once.
    assert execution_counter.read_text() == "1"

    attempts = [
        item
        for item in state.remediation_attempts(transaction_id)
        if item["position"] == 0
    ]

    assert len(attempts) == 2

    assert attempts[0]["attempt_number"] == 1
    assert attempts[0]["status"] == "success"
    assert attempts[0]["verified"] == 1

    assert attempts[1]["attempt_number"] == 2
    assert attempts[1]["status"] == "blocked"
    assert attempts[1]["verified"] == 0
    assert attempts[1]["return_code"] is None
    assert attempts[1]["timed_out"] == 0

    error = attempts[1]["error_message"].lower()

    assert "already available" in error
    assert "preservation policy" in error

    # The operational dependency remains intact.
    assert executable.exists()
