from pathlib import Path

import pytest

from kc_installer.cli import main
from kc_installer.engine import checksum_path
from kc_installer.state import InstallerState


def test_recover_rejects_missing_transaction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "KHAN_CLOUD_INSTALLER_STATE",
        str(tmp_path / "state"),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["kc-installer", "recover", "does-not-exist"],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert "not currently incomplete" in str(exc.value)


def test_recover_refuses_active_transaction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"

    monkeypatch.setenv(
        "KHAN_CLOUD_INSTALLER_STATE",
        str(state_root),
    )

    state = InstallerState(state_root / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-ACTIVE",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    monkeypatch.setattr(
        "sys.argv",
        ["kc-installer", "recover", transaction_id],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert "still active" in str(exc.value)


def test_recover_marks_interrupted_transaction_requested(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state"

    monkeypatch.setenv(
        "KHAN_CLOUD_INSTALLER_STATE",
        str(state_root),
    )

    state = InstallerState(state_root / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-INTERRUPTED",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    with state._connect() as db:
        db.execute(
            """
            UPDATE installations
            SET owner_pid = 2147483647
            WHERE transaction_id = ?
            """,
            (transaction_id,),
        )

    monkeypatch.setattr(
        "sys.argv",
        ["kc-installer", "recover", transaction_id],
    )

    main()

    journal = state.journal(transaction_id)

    assert journal[-1]["stage"] == "recovery_requested"
    assert journal[-1]["status"] == "pending"


def test_recover_cli_executes_guarded_rollback(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    import json
    import socket

    state_root = tmp_path / "state"
    backup_root = tmp_path / "backups" / "feature-packs"
    target = tmp_path / "target"

    target.mkdir()
    backup_root.mkdir(parents=True)

    monkeypatch.setenv(
        "KHAN_CLOUD_INSTALLER_STATE",
        str(state_root),
    )
    monkeypatch.setenv(
        "KHAN_CLOUD_INSTALLER_BACKUPS",
        str(backup_root),
    )

    state = InstallerState(state_root / "installer.db")

    backup = backup_root / "fp-cli-backup"
    backup.mkdir()

    existing = target / "existing.txt"
    existing.write_text("new-content")

    (backup / "existing.txt").write_text("old-content")

    transaction_id = state.begin(
        feature_pack_id="FP-CLI-RECOVERY",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=target,
        backup_path=backup,
        dry_run=False,
    )

    state.record_destinations(
        transaction_id,
        [(existing, True)],
    )

    state.record_backup_checksum(
        transaction_id,
        existing,
        checksum_path(backup / "existing.txt"),
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

    monkeypatch.setattr(
        "sys.argv",
        [
            "kc-installer",
            "recover",
            transaction_id,
            "--rollback",
        ],
    )

    main()

    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "recovered"
    assert output["transaction_id"] == transaction_id
    assert existing.read_text() == "old-content"

    installation = state.installation(transaction_id)

    assert installation is not None
    assert installation["status"] == "recovered"
