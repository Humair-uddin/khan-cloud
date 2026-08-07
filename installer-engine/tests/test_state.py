from pathlib import Path

from kc_installer.state import InstallerState


def test_state_records_successful_installation(tmp_path: Path) -> None:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-TEST",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    state.record(transaction_id, "validated", "success")
    state.record(transaction_id, "backup", "success")
    state.finish(
        transaction_id,
        status="success",
        stage="completed",
    )

    installation = state.installation(transaction_id)

    assert installation is not None
    assert installation["status"] == "success"
    assert installation["current_stage"] == "completed"

    journal = state.journal(transaction_id)

    assert [entry["stage"] for entry in journal] == [
        "started",
        "validated",
        "backup",
        "completed",
    ]


def test_state_records_failure(tmp_path: Path) -> None:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-FAIL",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    state.record(transaction_id, "activation", "started")

    state.finish(
        transaction_id,
        status="failed",
        stage="activation",
        error_message="simulated failure",
    )

    installation = state.installation(transaction_id)

    assert installation is not None
    assert installation["status"] == "failed"
    assert installation["error_message"] == "simulated failure"


def test_state_persists_structured_remediation_plan(tmp_path: Path) -> None:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-REMEDIATION",
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
            },
            {
                "dependency_name": "Example Tool",
                "action_type": "command",
                "command": [
                    "apt-get",
                    "install",
                    "-y",
                    "example-tool",
                ],
                "description": "Install example tool.",
            },
        ],
    )

    plan = state.remediation_plan(transaction_id)

    assert len(plan) == 2

    assert plan[0]["dependency_name"] == "Docker"
    assert plan[0]["action_type"] == "command"
    assert plan[0]["command"] == [
        "apt-get",
        "install",
        "-y",
        "docker.io",
    ]
    assert plan[0]["description"] == "Install Docker."
    assert plan[0]["position"] == 0
    assert plan[0]["eligible"] is None
    assert plan[0]["policy_reason"] is None

    assert plan[1]["dependency_name"] == "Example Tool"
    assert plan[1]["command"] == [
        "apt-get",
        "install",
        "-y",
        "example-tool",
    ]
    assert plan[1]["position"] == 1
    assert plan[1]["eligible"] is None
    assert plan[1]["policy_reason"] is None


def test_empty_remediation_plan_is_persisted_as_empty(tmp_path: Path) -> None:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-NO-REMEDIATION",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=True,
    )

    state.record_remediation_plan(transaction_id, [])

    assert state.remediation_plan(transaction_id) == []
