from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SpoolEntry:
    job_id: str
    payload: dict[str, Any]
    path: Path


class JobResultSpool:
    """Durable, atomic node-job result spool.

    A completed workload result is persisted before the control-plane report
    attempt. If the agent, host, or network dies after execution, the next
    heartbeat retries the exact result instead of blindly re-running the job.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, job_id: str) -> Path:
        safe = str(job_id).strip().replace("/", "_").replace("\\", "_")
        if not safe:
            raise ValueError("job_id is required")
        return self.root / f"{safe}.json"

    def save(self, job_id: str, payload: dict[str, Any]) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(job_id)
        tmp = path.with_suffix(".json.tmp")
        body = {
            "job_id": str(job_id),
            "payload": dict(payload),
        }
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(body, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        return path

    def pending(self) -> list[SpoolEntry]:
        if not self.root.exists():
            return []
        entries: list[SpoolEntry] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                job_id = str(raw.get("job_id") or "").strip()
                payload = raw.get("payload")
                if not job_id or not isinstance(payload, dict):
                    continue
                entries.append(
                    SpoolEntry(job_id=job_id, payload=dict(payload), path=path)
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
        return entries

    def remove(self, job_id: str) -> None:
        try:
            self._path(job_id).unlink()
        except FileNotFoundError:
            pass
