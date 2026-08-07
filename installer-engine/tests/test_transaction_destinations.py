from pathlib import Path

from kc_installer.state import InstallerState


def test_transaction_destinations_are_persistent(
    tmp_path: Path,
) -> None:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-DEST",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    existing = tmp_path / "target" / "existing.txt"
    new_file = tmp_path / "target" / "new.txt"

    state.record_destinations(
        transaction_id,
        [
            (existing, True),
            (new_file, False),
        ],
    )

    rows = state.destinations(transaction_id)

    assert len(rows) == 2

    assert rows[0]["destination_path"] == str(existing)
    assert rows[0]["existed_before"] == 1
    assert rows[0]["position"] == 0

    assert rows[1]["destination_path"] == str(new_file)
    assert rows[1]["existed_before"] == 0
    assert rows[1]["position"] == 1
