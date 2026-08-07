from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


_SECRET_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+"
)


@dataclass(frozen=True)
class InstallerTelemetrySnapshot:
    transaction_id: str
    feature_pack_id: str
    feature_pack_version: str
    status: str
    stage: str
    failure_category: str
    message: str
    reported_at: str

    def as_payload(self) -> dict[str, object]:
        return {
            "transaction_id": self.transaction_id,
            "feature_pack_id": self.feature_pack_id,
            "feature_pack_version": self.feature_pack_version,
            "status": self.status,
            "stage": self.stage,
            "failure_category": self.failure_category,
            "message": self.message,
            "reported_at": self.reported_at,
            "details": {"current_stage": self.stage},
        }


def sanitize_message(message: str) -> str:
    return _SECRET_PATTERN.sub(r"\1=[REDACTED]", message or "")[:500]


def failure_category(status: str, stage: str) -> str:
    lowered = f"{status} {stage}".lower()
    if status in {"success", "dry_run_success"}:
        return ""
    for category in (
        "preflight",
        "dependency",
        "remediation",
        "health",
        "rollback",
        "recovery",
        "interrupted",
        "activation",
    ):
        if category in lowered:
            return "health_check" if category == "health" else category
    if "fail" in lowered or "error" in lowered or "blocked" in lowered:
        return "unknown"
    return ""


def read_latest_installer_snapshot(database_path: Path) -> InstallerTelemetrySnapshot | None:
    if not database_path.exists():
        return None

    uri = f"file:{database_path}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                """
                SELECT
                    transaction_id,
                    feature_pack_id,
                    feature_pack_version,
                    status,
                    current_stage,
                    completed_at,
                    last_heartbeat_at,
                    started_at,
                    error_message
                FROM installations
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error:
        return None

    if row is None:
        return None

    reported_at = (
        row["completed_at"]
        or row["last_heartbeat_at"]
        or row["started_at"]
        or datetime.now(UTC).isoformat()
    )

    status = str(row["status"] or "unknown")
    stage = str(row["current_stage"] or "unknown")

    return InstallerTelemetrySnapshot(
        transaction_id=str(row["transaction_id"]),
        feature_pack_id=str(row["feature_pack_id"] or ""),
        feature_pack_version=str(row["feature_pack_version"] or ""),
        status=status,
        stage=stage,
        failure_category=failure_category(status, stage),
        message=sanitize_message(str(row["error_message"] or "")),
        reported_at=str(reported_at),
    )
