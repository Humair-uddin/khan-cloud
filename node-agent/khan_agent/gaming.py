from __future__ import annotations

from typing import Any

from khan_agent.virtualization import JobExecutionResult


def execute_gaming_job(job: dict[str, Any]) -> JobExecutionResult:
    """Execute Khan Cloud gaming workload operations."""

    job_type = str(job.get("job_type", "")).strip()

    if job_type == "gaming.probe":
        return JobExecutionResult(
            "succeeded",
            {
                "workload_family": "gaming",
                "executor": "khan_agent.gaming",
                "probe": "ok",
            },
        )

    return JobExecutionResult(
        "failed",
        {},
        f"Unsupported gaming job type: {job_type or '<empty>'}.",
    )
