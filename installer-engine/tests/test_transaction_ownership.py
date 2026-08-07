import os
import socket
from pathlib import Path

from kc_installer.state import InstallerState


def test_transaction_records_process_ownership(
    tmp_path: Path,
) -> None:
    state = InstallerState(tmp_path / "installer.db")

    transaction_id = state.begin(
        feature_pack_id="FP-OWNER",
        feature_pack_version="1.0.0",
        package_path=tmp_path / "package",
        target_path=tmp_path / "target",
        backup_path=tmp_path / "backup",
        dry_run=False,
    )

    installation = state.installation(transaction_id)

    assert installation is not None
    assert installation["owner_pid"] == os.getpid()
    assert installation["owner_hostname"] == socket.gethostname()
    assert installation["last_heartbeat_at"] is not None

    previous = installation["last_heartbeat_at"]

    state.heartbeat(transaction_id)

    updated = state.installation(transaction_id)

    assert updated is not None
    assert updated["last_heartbeat_at"] >= previous
