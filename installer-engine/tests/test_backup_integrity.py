from pathlib import Path

import pytest

from kc_installer.engine import (
    InstallError,
    checksum_path,
    recover_transaction,
)
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


def test_recovery_refuses_tampered_backup(tmp_path: Path) -> None:
    import socket

    paths = make_paths(tmp_path / "khan-cloud")
    paths.ensure_directories()

    target = tmp_path / "target"
    target.mkdir()

    destination = target / "important.txt"
    destination.write_text("new-version")

    backup_root = paths.backup_root / "fp-integrity"
    backup_root.mkdir(parents=True)

    backup = backup_root / "important.txt"
    backup.write_text("original-version")

    state = InstallerState(paths.database_path)

    transaction_id = state.begin(
        feature_pack_id="FP-INTEGRITY",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=target,
        backup_path=backup_root,
        dry_run=False,
    )

    state.record_destinations(
        transaction_id,
        [(destination, True)],
    )

    state.record_backup_checksum(
        transaction_id,
        destination,
        checksum_path(backup),
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

    backup.write_text("CORRUPTED")

    with pytest.raises(
        InstallError,
        match="backup integrity check failed",
    ):
        recover_transaction(
            transaction_id,
            paths=paths,
        )

    assert destination.read_text() == "new-version"
