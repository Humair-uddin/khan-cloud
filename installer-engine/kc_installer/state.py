from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class InstallerState:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS installations (
                    transaction_id TEXT PRIMARY KEY,
                    feature_pack_id TEXT NOT NULL,
                    feature_pack_version TEXT NOT NULL,
                    package_path TEXT NOT NULL,
                    target_path TEXT NOT NULL,
                    backup_path TEXT,
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    current_stage TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(transaction_id)
                        REFERENCES installations(transaction_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS
                    idx_journal_transaction
                ON journal(transaction_id, id);
                """
            )

    def begin(
        self,
        *,
        feature_pack_id: str,
        feature_pack_version: str,
        package_path: Path,
        target_path: Path,
        backup_path: Path,
        dry_run: bool,
    ) -> str:
        transaction_id = str(uuid.uuid4())
        now = utc_now()

        with self._connect() as db:
            db.execute(
                """
                INSERT INTO installations (
                    transaction_id,
                    feature_pack_id,
                    feature_pack_version,
                    package_path,
                    target_path,
                    backup_path,
                    dry_run,
                    status,
                    current_stage,
                    started_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    feature_pack_id,
                    feature_pack_version,
                    str(package_path),
                    str(target_path),
                    str(backup_path),
                    int(dry_run),
                    "running",
                    "started",
                    now,
                ),
            )

            db.execute(
                """
                INSERT INTO journal (
                    transaction_id,
                    stage,
                    status,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    "started",
                    "success",
                    "",
                    now,
                ),
            )

        return transaction_id

    def record(
        self,
        transaction_id: str,
        stage: str,
        status: str,
        message: str = "",
    ) -> None:
        now = utc_now()

        with self._connect() as db:
            db.execute(
                """
                INSERT INTO journal (
                    transaction_id,
                    stage,
                    status,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    stage,
                    status,
                    message,
                    now,
                ),
            )

            db.execute(
                """
                UPDATE installations
                SET current_stage = ?
                WHERE transaction_id = ?
                """,
                (stage, transaction_id),
            )

    def finish(
        self,
        transaction_id: str,
        *,
        status: str,
        stage: str,
        error_message: str = "",
    ) -> None:
        now = utc_now()

        with self._connect() as db:
            db.execute(
                """
                UPDATE installations
                SET
                    status = ?,
                    current_stage = ?,
                    completed_at = ?,
                    error_message = ?
                WHERE transaction_id = ?
                """,
                (
                    status,
                    stage,
                    now,
                    error_message,
                    transaction_id,
                ),
            )

            db.execute(
                """
                INSERT INTO journal (
                    transaction_id,
                    stage,
                    status,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    stage,
                    status,
                    error_message,
                    now,
                ),
            )

    def installation(self, transaction_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                """
                SELECT *
                FROM installations
                WHERE transaction_id = ?
                """,
                (transaction_id,),
            ).fetchone()

        return dict(row) if row else None

    def journal(self, transaction_id: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT *
                FROM journal
                WHERE transaction_id = ?
                ORDER BY id
                """,
                (transaction_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    def installations(self, limit: int = 20) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT *
                FROM installations
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [dict(row) for row in rows]
