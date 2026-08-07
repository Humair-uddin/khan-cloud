import json
import sys
from pathlib import Path

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


def test_show_cli_exposes_persisted_remediation_plan(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    paths = make_paths(tmp_path / "khan-cloud")
    state = InstallerState(paths.database_path)

    transaction_id = state.begin(
        feature_pack_id="FP-SHOW-REMEDIATION",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=True,
    )

    state.record_remediation_plan(
        transaction_id,
        [
            {
                "dependency_name": "Docker",
                "action_type": "command",
                "command": [
                    "apt-get",
                    "install",
                    "-y",
                    "docker.io",
                ],
                "description": "Install Docker.",
            }
        ],
    )

    monkeypatch.setattr(
        InstallerPaths,
        "from_environment",
        classmethod(lambda cls: paths),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kc-installer",
            "show",
            transaction_id,
        ],
    )

    main()

    output = json.loads(capsys.readouterr().out)

    assert output["installation"]["transaction_id"] == transaction_id

    assert output["remediation_plan"] == [
        {
            "dependency_name": "Docker",
            "action_type": "command",
            "command": [
                "apt-get",
                "install",
                "-y",
                "docker.io",
            ],
            "description": "Install Docker.",
            "position": 0,
            "eligible": None,
            "policy_reason": None,
        }
    ]


def test_show_cli_exposes_remediation_attempts(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    paths = make_paths(tmp_path / "khan-cloud")
    state = InstallerState(paths.database_path)

    transaction_id = state.begin(
        feature_pack_id="FP-SHOW-ATTEMPT",
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
                "dependency_name": "Docker",
                "action_type": "command",
                "command": ["echo", "test"],
                "description": "Test.",
                "eligible": True,
                "policy_reason": "eligible",
            }
        ],
    )

    attempt_id = state.begin_remediation_attempt(
        transaction_id,
        0,
    )

    state.finish_remediation_attempt(
        attempt_id,
        status="success",
        return_code=0,
        stdout="ok\n",
        verified=True,
    )

    monkeypatch.setattr(
        InstallerPaths,
        "from_environment",
        classmethod(lambda cls: paths),
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kc-installer",
            "show",
            transaction_id,
        ],
    )

    main()

    output = json.loads(capsys.readouterr().out)

    assert len(output["remediation_attempts"]) == 1

    attempt = output["remediation_attempts"][0]

    assert attempt["dependency_name"] == "Docker"
    assert attempt["attempt_number"] == 1
    assert attempt["status"] == "success"
    assert attempt["return_code"] == 0
    assert attempt["verified"] is True
    assert attempt["stdout"] == "ok\n"
