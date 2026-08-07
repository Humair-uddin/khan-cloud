from __future__ import annotations

import os
import socket
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

            columns = {
                row["name"]
                for row in db.execute(
                    "PRAGMA table_info(installations)"
                ).fetchall()
            }

            additions = {
                "owner_pid": "INTEGER",
                "owner_hostname": "TEXT",
                "last_heartbeat_at": "TEXT",
            }

            for name, sql_type in additions.items():
                if name not in columns:
                    db.execute(
                        f"ALTER TABLE installations "
                        f"ADD COLUMN {name} {sql_type}"
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
                    started_at,
                    owner_pid,
                    owner_hostname,
                    last_heartbeat_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    os.getpid(),
                    socket.gethostname(),
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

    def incomplete_installations(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT *
                FROM installations
                WHERE status = 'running'
                ORDER BY started_at ASC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def mark_interrupted(
        self,
        transaction_id: str,
        message: str = "Installer process ended before transaction completion.",
    ) -> None:
        self.finish(
            transaction_id,
            status="interrupted",
            stage="interrupted",
            error_message=message,
        )

    def heartbeat(self, transaction_id: str) -> None:
        now = utc_now()

        with self._connect() as db:
            db.execute(
                """
                UPDATE installations
                SET last_heartbeat_at = ?
                WHERE transaction_id = ?
                  AND status = 'running'
                """,
                (now, transaction_id),
            )

    def classify_incomplete(
        self,
        *,
        stale_after_seconds: int = 300,
    ) -> list[dict]:
        import os
        import socket
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        local_hostname = socket.gethostname()
        results = []

        for item in self.incomplete_installations():
            classification = "unknown"
            reason = "Unable to verify transaction owner."

            heartbeat_raw = item.get("last_heartbeat_at")
            owner_hostname = item.get("owner_hostname")
            owner_pid = item.get("owner_pid")

            heartbeat_age = None

            if heartbeat_raw:
                heartbeat = datetime.fromisoformat(heartbeat_raw)
                heartbeat_age = (
                    now - heartbeat
                ).total_seconds()

            if owner_hostname == local_hostname and owner_pid:
                try:
                    os.kill(int(owner_pid), 0)
                    process_alive = True
                except ProcessLookupError:
                    process_alive = False
                except PermissionError:
                    process_alive = True

                if process_alive:
                    classification = "active"
                    reason = "Owner process is still running."
                else:
                    classification = "interrupted"
                    reason = "Owner process no longer exists."

            elif heartbeat_age is not None:
                if heartbeat_age > stale_after_seconds:
                    classification = "stale"
                    reason = (
                        "Heartbeat exceeded stale threshold."
                    )
                else:
                    classification = "recent_remote"
                    reason = (
                        "Transaction belongs to another host "
                        "and heartbeat is still recent."
                    )

            results.append(
                {
                    **item,
                    "classification": classification,
                    "reason": reason,
                    "heartbeat_age_seconds": heartbeat_age,
                }
            )

        return results
