from __future__ import annotations

from pathlib import Path
from typing import Any

from khan_agent.gaming import execute_gaming_job
from khan_agent.virtualization import JobExecutionResult, execute_virtualization_job


def execute_node_job(
    job: dict[str, Any],
    *,
    virtualization_execution_enabled: bool,
    virtualization_storage_root: Path,
    virtualization_base_image_path: Path,
    virtualization_network_name: str,
    gaming_execution_enabled: bool = False,
    gaming_execution_backend: str = "none",
    gaming_streaming_backend: str = "none",
    gaming_state_root: Path = Path("/var/lib/khan-cloud-agent/gaming"),
) -> JobExecutionResult:
    """Route a node job to the executor responsible for its workload family."""

    job_type = str(job.get("job_type", "")).strip()

    if job_type.startswith("vps."):
        return execute_virtualization_job(
            job,
            execution_enabled=virtualization_execution_enabled,
            storage_root=virtualization_storage_root,
            base_image_path=virtualization_base_image_path,
            network_name=virtualization_network_name,
        )

    if job_type.startswith("gaming."):
        return execute_gaming_job(
            job,
            execution_enabled=gaming_execution_enabled,
            execution_backend=gaming_execution_backend,
            streaming_backend=gaming_streaming_backend,
            state_root=gaming_state_root,
        )

    return JobExecutionResult(
        "failed",
        {},
        f"Unsupported node job type: {job_type or '<empty>'}.",
    )
