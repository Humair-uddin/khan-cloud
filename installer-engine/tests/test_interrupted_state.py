from pathlib import Path

from kc_installer.state import InstallerState


def test_detect_and_mark_interrupted_installation(
    tmp_path: Path,
) -> None:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-INTERRUPT",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    state.record(
        transaction_id,
        "activated",
        "success",
    )

    incomplete = state.incomplete_installations()

    assert len(incomplete) == 1
    assert incomplete[0]["transaction_id"] == transaction_id
    assert incomplete[0]["current_stage"] == "activated"

    state.mark_interrupted(transaction_id)

    installation = state.installation(transaction_id)

    assert installation is not None
    assert installation["status"] == "interrupted"
    assert installation["current_stage"] == "interrupted"

    assert state.incomplete_installations() == []

    journal = state.journal(transaction_id)

    assert journal[-1]["stage"] == "interrupted"
    assert journal[-1]["status"] == "interrupted"
