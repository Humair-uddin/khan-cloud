from pathlib import Path

import pytest

from kc_installer.cli import main
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
