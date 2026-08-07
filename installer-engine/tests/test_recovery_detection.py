import os
import socket
from pathlib import Path

from kc_installer.state import InstallerState


def begin_transaction(
    state: InstallerState,
    tmp_path: Path,
) -> str:
    return state.begin(
        feature_pack_id="FP-RECOVERY",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )


def test_current_process_is_classified_active(
    tmp_path: Path,
) -> None:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = begin_transaction(state, tmp_path)

    result = state.classify_incomplete()

    assert len(result) == 1
    assert result[0]["transaction_id"] == transaction_id
    assert result[0]["classification"] == "active"


def test_missing_local_process_is_interrupted(
    tmp_path: Path,
) -> None:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = begin_transaction(state, tmp_path)

    with state._connect() as db:
        db.execute(
            """
            UPDATE installations
            SET owner_pid = ?,
                owner_hostname = ?
            WHERE transaction_id = ?
            """,
            (
                2147483647,
                socket.gethostname(),
                transaction_id,
            ),
        )

    result = state.classify_incomplete()

    assert result[0]["classification"] == "interrupted"
