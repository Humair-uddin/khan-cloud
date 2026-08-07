import socket
from pathlib import Path

import pytest

from kc_installer.engine import InstallError, recover_transaction
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


def prepare_interrupted_transaction(
    tmp_path: Path,
) -> tuple[
    InstallerPaths,
    InstallerState,
    str,
    Path,
    Path,
]:
    root = tmp_path / "khan-cloud"
    paths = make_paths(root)
    paths.ensure_directories()

    target = tmp_path / "target"
    target.mkdir()

    backup = paths.backup_root / "fp-test-backup"
    backup.mkdir(parents=True)

    state = InstallerState(paths.database_path)

    transaction_id = state.begin(
        feature_pack_id="FP-ROLLBACK",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=target,
        backup_path=backup,
        dry_run=False,
    )

    existing = target / "existing.txt"
    existing.write_text("new-content")

    newly_created = target / "new.txt"
    newly_created.write_text("new-file")

    backup_existing = backup / "existing.txt"
    backup_existing.write_text("old-content")

    state.record_destinations(
        transaction_id,
        [
            (existing, True),
            (newly_created, False),
        ],
    )

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

    return (
        paths,
        state,
        transaction_id,
        existing,
        newly_created,
    )


def test_recovery_restores_previous_state(
    tmp_path: Path,
) -> None:
    (
        paths,
        state,
        transaction_id,
        existing,
        newly_created,
    ) = prepare_interrupted_transaction(tmp_path)

    result = recover_transaction(
        transaction_id,
        paths=paths,
    )

    assert result["status"] == "recovered"

    assert existing.read_text() == "old-content"
    assert not newly_created.exists()

    installation = state.installation(transaction_id)

    assert installation is not None
    assert installation["status"] == "recovered"
    assert installation["current_stage"] == "recovered"


def test_recovery_refuses_missing_required_backup(
    tmp_path: Path,
) -> None:
    (
        paths,
        state,
        transaction_id,
        existing,
        _,
    ) = prepare_interrupted_transaction(tmp_path)

    installation = state.installation(transaction_id)
    assert installation is not None

    backup_root = Path(installation["backup_path"])
    (backup_root / "existing.txt").unlink()

    with pytest.raises(
        InstallError,
        match="required backup is missing",
    ):
        recover_transaction(
            transaction_id,
            paths=paths,
        )

    assert existing.read_text() == "new-content"
