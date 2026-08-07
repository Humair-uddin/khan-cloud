from __future__ import annotations

import json
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
        self.update_destination_schema()
        self.update_remediation_schema()
        self.update_trust_schema()

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

                CREATE TABLE IF NOT EXISTS transaction_destinations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT NOT NULL,
                    destination_path TEXT NOT NULL,
                    existed_before INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    FOREIGN KEY(transaction_id)
                        REFERENCES installations(transaction_id)
                        ON DELETE CASCADE,
                    UNIQUE(transaction_id, destination_path)
                );

                CREATE INDEX IF NOT EXISTS
                    idx_transaction_destinations
                ON transaction_destinations(transaction_id, position);

                CREATE TABLE IF NOT EXISTS transaction_remediation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT NOT NULL,
                    dependency_name TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    position INTEGER NOT NULL,
                    FOREIGN KEY(transaction_id)
                        REFERENCES installations(transaction_id)
                        ON DELETE CASCADE,
                    UNIQUE(transaction_id, position)
                );

                CREATE INDEX IF NOT EXISTS
                    idx_transaction_remediation_actions
                ON transaction_remediation_actions(
                    transaction_id,
                    position
                );

                CREATE TABLE IF NOT EXISTS remediation_execution_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT NOT NULL,
                    remediation_action_id INTEGER NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    return_code INTEGER,
                    timed_out INTEGER NOT NULL DEFAULT 0,
                    stdout TEXT NOT NULL DEFAULT '',
                    stderr TEXT NOT NULL DEFAULT '',
                    verified INTEGER,
                    error_message TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(transaction_id)
                        REFERENCES installations(transaction_id)
                        ON DELETE CASCADE,
                    FOREIGN KEY(remediation_action_id)
                        REFERENCES transaction_remediation_actions(id)
                        ON DELETE CASCADE,
                    UNIQUE(remediation_action_id, attempt_number)
                );

                CREATE INDEX IF NOT EXISTS
                    idx_remediation_execution_attempts
                ON remediation_execution_attempts(
                    transaction_id,
                    remediation_action_id,
                    attempt_number
                );
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

    def record_destinations(
        self,
        transaction_id: str,
        destinations: list[tuple[Path, bool]],
    ) -> None:
        with self._connect() as db:
            for position, (destination, existed_before) in enumerate(
                destinations
            ):
                db.execute(
                    """
                    INSERT INTO transaction_destinations (
                        transaction_id,
                        destination_path,
                        existed_before,
                        position
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        transaction_id,
                        str(destination),
                        int(existed_before),
                        position,
                    ),
                )

    def record_remediation_plan(
        self,
        transaction_id: str,
        actions: list[dict],
    ) -> None:
        with self._connect() as db:
            existing_attempt = db.execute(
                """
                SELECT 1
                FROM remediation_execution_attempts
                WHERE transaction_id = ?
                LIMIT 1
                """,
                (transaction_id,),
            ).fetchone()

            if existing_attempt is not None:
                raise ValueError(
                    "Cannot replace remediation plan after "
                    "execution attempts have been recorded."
                )

            db.execute(
                """
                DELETE FROM transaction_remediation_actions
                WHERE transaction_id = ?
                """,
                (transaction_id,),
            )

            for position, action in enumerate(actions):
                db.execute(
                    """
                    INSERT INTO transaction_remediation_actions (
                        transaction_id,
                        dependency_name,
                        action_type,
                        command_json,
                        description,
                        position,
                        eligible,
                        policy_reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transaction_id,
                        action["dependency_name"],
                        action["action_type"],
                        json.dumps(action["command"]),
                        action.get("description", ""),
                        position,
                        (
                            int(action["eligible"])
                            if action.get("eligible") is not None
                            else None
                        ),
                        action.get("policy_reason"),
                    ),
                )

    def remediation_plan(self, transaction_id: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT
                    dependency_name,
                    action_type,
                    command_json,
                    description,
                    position,
                    eligible,
                    policy_reason
                FROM transaction_remediation_actions
                WHERE transaction_id = ?
                ORDER BY position
                """,
                (transaction_id,),
            ).fetchall()

        return [
            {
                "dependency_name": row["dependency_name"],
                "action_type": row["action_type"],
                "command": json.loads(row["command_json"]),
                "description": row["description"],
                "position": row["position"],
                "eligible": (
                    bool(row["eligible"])
                    if row["eligible"] is not None
                    else None
                ),
                "policy_reason": row["policy_reason"],
            }
            for row in rows
        ]

    def begin_remediation_attempt(
        self,
        transaction_id: str,
        position: int,
    ) -> int:
        now = utc_now()

        with self._connect() as db:
            action = db.execute(
                """
                SELECT
                    id,
                    dependency_name
                FROM transaction_remediation_actions
                WHERE transaction_id = ?
                  AND position = ?
                """,
                (transaction_id, position),
            ).fetchone()

            if action is None:
                raise ValueError(
                    "Remediation action not found for "
                    f"transaction {transaction_id}, position {position}."
                )

            row = db.execute(
                """
                SELECT COALESCE(MAX(attempt_number), 0) + 1
                FROM remediation_execution_attempts
                WHERE remediation_action_id = ?
                """,
                (action["id"],),
            ).fetchone()

            attempt_number = int(row[0])

            cursor = db.execute(
                """
                INSERT INTO remediation_execution_attempts (
                    transaction_id,
                    remediation_action_id,
                    attempt_number,
                    status,
                    started_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    action["id"],
                    attempt_number,
                    "running",
                    now,
                ),
            )

            attempt_id = int(cursor.lastrowid)

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
                    "remediation_execution",
                    "started",
                    (
                        f"{action['dependency_name']}: "
                        f"attempt {attempt_number} started"
                    ),
                    now,
                ),
            )

        return attempt_id

    def finish_remediation_attempt(
        self,
        attempt_id: int,
        *,
        status: str,
        return_code: int | None = None,
        timed_out: bool = False,
        stdout: str = "",
        stderr: str = "",
        verified: bool | None = None,
        error_message: str = "",
    ) -> None:
        now = utc_now()

        with self._connect() as db:
            attempt = db.execute(
                """
                SELECT
                    attempts.transaction_id,
                    attempts.attempt_number,
                    actions.dependency_name
                FROM remediation_execution_attempts AS attempts
                JOIN transaction_remediation_actions AS actions
                  ON actions.id = attempts.remediation_action_id
                WHERE attempts.id = ?
                """,
                (attempt_id,),
            ).fetchone()

            if attempt is None:
                raise ValueError(
                    f"Remediation execution attempt not found: {attempt_id}"
                )

            db.execute(
                """
                UPDATE remediation_execution_attempts
                SET
                    status = ?,
                    completed_at = ?,
                    return_code = ?,
                    timed_out = ?,
                    stdout = ?,
                    stderr = ?,
                    verified = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    status,
                    now,
                    return_code,
                    int(timed_out),
                    stdout,
                    stderr,
                    (
                        int(verified)
                        if verified is not None
                        else None
                    ),
                    error_message,
                    attempt_id,
                ),
            )

            message = (
                f"{attempt['dependency_name']}: "
                f"attempt {attempt['attempt_number']} {status}"
            )

            if error_message:
                message += f": {error_message}"

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
                    attempt["transaction_id"],
                    "remediation_execution",
                    status,
                    message,
                    now,
                ),
            )

    def remediation_attempts(
        self,
        transaction_id: str,
    ) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT
                    attempts.id,
                    attempts.attempt_number,
                    attempts.status,
                    attempts.started_at,
                    attempts.completed_at,
                    attempts.return_code,
                    attempts.timed_out,
                    attempts.stdout,
                    attempts.stderr,
                    attempts.verified,
                    attempts.error_message,
                    actions.dependency_name,
                    actions.position
                FROM remediation_execution_attempts AS attempts
                JOIN transaction_remediation_actions AS actions
                  ON actions.id = attempts.remediation_action_id
                WHERE attempts.transaction_id = ?
                ORDER BY
                    actions.position,
                    attempts.attempt_number
                """,
                (transaction_id,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "dependency_name": row["dependency_name"],
                "position": row["position"],
                "attempt_number": row["attempt_number"],
                "status": row["status"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "return_code": row["return_code"],
                "timed_out": bool(row["timed_out"]),
                "stdout": row["stdout"],
                "stderr": row["stderr"],
                "verified": (
                    bool(row["verified"])
                    if row["verified"] is not None
                    else None
                ),
                "error_message": row["error_message"],
            }
            for row in rows
        ]

    def destinations(self, transaction_id: str) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT
                    destination_path,
                    existed_before,
                    position,
                    backup_checksum
                FROM transaction_destinations
                WHERE transaction_id = ?
                ORDER BY position
                """,
                (transaction_id,),
            ).fetchall()

        return [dict(row) for row in rows]

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

    def mark_recovery_requested(
        self,
        transaction_id: str,
        message: str = "Recovery requested by administrator.",
    ) -> None:
        self.record(
            transaction_id,
            "recovery_requested",
            "pending",
            message,
        )

    def record_backup_checksum(
        self,
        transaction_id: str,
        destination_path: Path,
        checksum: str,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE transaction_destinations
                SET backup_checksum = ?
                WHERE transaction_id = ?
                  AND destination_path = ?
                """,
                (
                    checksum,
                    transaction_id,
                    str(destination_path),
                ),
            )


    def record_package_trust(
        self,
        transaction_id: str,
        *,
        trusted: bool,
        signer_id: str | None,
        package_digest: str,
        trust_reason: str,
    ) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE installations
                SET package_trusted = ?, signer_id = ?,
                    package_digest = ?, trust_reason = ?
                WHERE transaction_id = ?
                """,
                (int(trusted), signer_id, package_digest, trust_reason, transaction_id),
            )
        self.record(
            transaction_id,
            "package_trust",
            "trusted" if trusted else "untrusted",
            f"{signer_id or 'unsigned'}: {trust_reason}",
        )

    def interrupt_running_remediation_attempts(
        self, transaction_id: str | None = None
    ) -> int:
        now = utc_now()
        with self._connect() as db:
            params: tuple = ()
            where = "status = 'running'"
            if transaction_id is not None:
                where += " AND transaction_id = ?"
                params = (transaction_id,)
            rows = db.execute(
                f"SELECT id FROM remediation_execution_attempts WHERE {where}", params
            ).fetchall()
            for row in rows:
                db.execute(
                    """UPDATE remediation_execution_attempts
                    SET status='interrupted', completed_at=?, verified=0,
                        error_message='Execution interrupted before completion.'
                    WHERE id=?""",
                    (now, row["id"]),
                )
        return len(rows)

    def update_trust_schema(self) -> None:
        with self._connect() as db:
            columns = {row["name"] for row in db.execute(
                "PRAGMA table_info(installations)"
            ).fetchall()}
            additions = {
                "package_trusted": "INTEGER",
                "signer_id": "TEXT",
                "package_digest": "TEXT",
                "trust_reason": "TEXT",
            }
            for name, sql_type in additions.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE installations ADD COLUMN {name} {sql_type}")

    def update_remediation_schema(self) -> None:
        with self._connect() as db:
            columns = {
                row["name"]
                for row in db.execute(
                    "PRAGMA table_info(transaction_remediation_actions)"
                ).fetchall()
            }

            additions = {
                "eligible": "INTEGER",
                "policy_reason": "TEXT",
            }

            for name, sql_type in additions.items():
                if name not in columns:
                    db.execute(
                        "ALTER TABLE transaction_remediation_actions "
                        f"ADD COLUMN {name} {sql_type}"
                    )

    def update_destination_schema(self) -> None:
        with self._connect() as db:
            columns = {
                row["name"]
                for row in db.execute(
                    "PRAGMA table_info(transaction_destinations)"
                ).fetchall()
            }

            if "backup_checksum" not in columns:
                db.execute(
                    """
                    ALTER TABLE transaction_destinations
                    ADD COLUMN backup_checksum TEXT
                    """
                )
