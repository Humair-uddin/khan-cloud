"""Best-effort, bounded launch timing records; never a launch authority."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import time
from typing import Any


_LOG = logging.getLogger("khan_agent.launch_diagnostics")


class LaunchTrace:
    def __init__(
        self, attempt_id: str = "", runtime_id: str = "",
        *, started_monotonic: float | None = None,
    ) -> None:
        self.attempt_id = str(attempt_id or "")[:80]
        self.runtime_id = str(runtime_id or "")[:80]
        self.started = (
            time.monotonic()
            if started_monotonic is None else started_monotonic
        )
        self.previous = self.started

    def emit(self, stage: str, **facts: Any) -> None:
        try:
            now = time.monotonic()
            record = {
                "stage": stage,
                "attempt_id": self.attempt_id,
                "runtime_id": self.runtime_id,
                "utc": datetime.now(timezone.utc).isoformat(),
                "monotonic_ms": round(now * 1000),
                "elapsed_ms": round((now - self.started) * 1000),
                "delta_ms": round((now - self.previous) * 1000),
                **facts,
            }
            self.previous = now
            _LOG.info("launch_stage %s", record)
        except Exception:
            pass
