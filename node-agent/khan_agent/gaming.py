from __future__ import annotations

from pathlib import Path
from typing import Any

from khan_agent.gaming_backends import probe_gaming_backend, probe_proxmox_vm
from khan_agent.gaming_runtime import change_session_state, create_session
from khan_agent.virtualization import JobExecutionResult


def execute_gaming_job(
    job: dict[str, Any],
    *,
    execution_enabled: bool = False,
    execution_backend: str = "none",
    streaming_backend: str = "none",
    state_root: Path = Path("/var/lib/khan-cloud-agent/gaming"),
) -> JobExecutionResult:
    """Execute Khan Cloud gaming workload operations."""

    job_type = str(job.get("job_type", "")).strip()

    if job_type == "gaming.probe":
        backend = probe_gaming_backend(execution_backend)
        payload = job.get("payload") or {}

        result: dict[str, Any] = {
            "workload_family": "gaming",
            "executor": "khan_agent.gaming",
            "execution_backend": execution_backend,
            "streaming_backend": streaming_backend,
            "backend": backend,
        }

        vm_id = payload.get("vm_id")

        if execution_backend == "proxmox_vm" and vm_id is not None:
            try:
                normalized_vm_id = int(vm_id)
            except (TypeError, ValueError):
                return JobExecutionResult(
                    "failed",
                    {},
                    "gaming.probe vm_id must be an integer.",
                )

            if normalized_vm_id <= 0:
                return JobExecutionResult(
                    "failed",
                    {},
                    "gaming.probe vm_id must be greater than zero.",
                )

            result["vm"] = probe_proxmox_vm(normalized_vm_id)

        return JobExecutionResult("succeeded", result)

    lifecycle = {
        "gaming.session.create",
        "gaming.session.start",
        "gaming.session.stop",
        "gaming.session.delete",
    }
    if job_type in lifecycle:
        if not execution_enabled:
            return JobExecutionResult(
                "blocked",
                {},
                "Gaming execution is disabled by node policy.",
            )
        payload = job.get("payload") or {}
        if not isinstance(payload, dict):
            return JobExecutionResult("failed", {}, "Gaming job payload must be an object.")
        if job_type == "gaming.session.create":
            return create_session(
                payload,
                state_root=state_root,
                execution_backend=execution_backend,
                streaming_backend=streaming_backend,
            )
        action = job_type.rsplit(".", 1)[-1]
        return change_session_state(
            payload,
            state_root=state_root,
            execution_backend=execution_backend,
            streaming_backend=streaming_backend,
            action=action,
        )

    return JobExecutionResult(
        "failed",
        {},
        f"Unsupported gaming job type: {job_type or '<empty>'}.",
    )
