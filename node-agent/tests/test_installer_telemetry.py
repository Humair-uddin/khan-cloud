import sqlite3
from pathlib import Path

from khan_agent.installer_telemetry import (
    failure_category,
    read_latest_installer_snapshot,
    sanitize_message,
)


def create_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TABLE installations (
                transaction_id TEXT PRIMARY KEY,
                feature_pack_id TEXT NOT NULL,
                feature_pack_version TEXT NOT NULL,
                status TEXT NOT NULL,
                current_stage TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                last_heartbeat_at TEXT,
                error_message TEXT
            )
            """
        )
        db.execute(
            """
            INSERT INTO installations VALUES (
                'tx-1', 'FP-TEST', '1.0.0', 'preflight_failed',
                'preflight', '2026-08-08T00:00:00+00:00',
                '2026-08-08T00:01:00+00:00', NULL,
                'token=secret-value compatibility failed'
            )
            """
        )


def test_latest_installer_snapshot_is_sanitized(tmp_path: Path) -> None:
    db = tmp_path / "installer.db"
    create_db(db)
    snapshot = read_latest_installer_snapshot(db)
    assert snapshot is not None
    assert snapshot.transaction_id == "tx-1"
    assert snapshot.status == "preflight_failed"
    assert snapshot.stage == "preflight"
    assert snapshot.failure_category == "preflight"
    assert "secret-value" not in snapshot.message


def test_missing_database_returns_none(tmp_path: Path) -> None:
    assert read_latest_installer_snapshot(tmp_path / "missing.db") is None


def test_failure_category_is_bounded() -> None:
    assert failure_category("dependency_blocked", "dependency") == "dependency"
    assert failure_category("success", "completed") == ""


def test_sanitizer_redacts_token() -> None:
    assert "secret" not in sanitize_message("token=secret")
