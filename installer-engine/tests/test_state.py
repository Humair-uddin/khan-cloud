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
