from __future__ import annotations

from pathlib import Path
from typing import Any

from khan_agent.gaming_backends import probe_gaming_backend, probe_proxmox_vm
from khan_agent.gaming_runtime import (
    change_session_state,
    create_session,
    pair_connection,
    revoke_connection,
)
from khan_agent.vdd_runtime_policy import (
    VddRuntimePolicyError,
    apply_display_policy,
    restore_last_known_good,
)
from khan_agent.virtualization import JobExecutionResult


def execute_gaming_job(
    job: dict[str, Any],
    *,
    execution_enabled: bool = False,
    execution_backend: str = "none",
    streaming_backend: str = "none",
    state_root: Path = Path("/var/lib/khan-cloud-agent/gaming"),
    sunshine_api_url: str = "https://127.0.0.1:47990",
    sunshine_api_username: str = "",
    sunshine_api_password: str = "",
    sunshine_verify_tls: bool = False,
    vdd_template_path: Path = Path(
        "C:/ProgramData/KhanCloud/VirtualDisplay/"
        "RuntimeConfig/khan-vdd-settings.xml"
    ),
    vdd_target_root: Path = Path(
        "C:/ProgramData/KhanCloud/VirtualDisplay"
    ),
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

    if job_type.startswith("gaming.display.policy."):
        if not execution_enabled:
            return JobExecutionResult(
                "blocked",
                {},
                "Gaming execution is disabled by node policy.",
            )

        payload = job.get("payload") or {}

        if not isinstance(payload, dict):
            return JobExecutionResult(
                "failed",
                {},
                "Gaming display policy payload must be an object.",
            )

        try:
            if job_type == "gaming.display.policy.apply":
                result = apply_display_policy(
                    payload,
                    template_path=vdd_template_path,
                    target_root=vdd_target_root,
                )
                return JobExecutionResult(
                    "succeeded",
                    result,
                )

            if job_type == "gaming.display.policy.restore":
                restored = restore_last_known_good(
                    target_root=vdd_target_root,
                )
                return JobExecutionResult(
                    "succeeded",
                    {
                        "restored": True,
                        "settings_path": str(restored),
                    },
                )

            return JobExecutionResult(
                "failed",
                {},
                f"Unsupported gaming display policy job type: {job_type}.",
            )

        except VddRuntimePolicyError as exc:
            return JobExecutionResult(
                "blocked",
                {},
                str(exc),
            )

    if (
        job_type.startswith("gaming.connection.")
        and not execution_enabled
    ):
        return JobExecutionResult(
            "blocked",
            {},
            "Gaming execution is disabled by node policy.",
        )

    if job_type == "gaming.connection.pair":
        payload = job.get("payload") or {}

        if not isinstance(payload, dict):
            return JobExecutionResult(
                "failed",
                {},
                "Gaming connection payload must be an object.",
            )

        return pair_connection(
            payload,
            state_root=state_root,
            sunshine_api_url=sunshine_api_url,
            sunshine_api_username=sunshine_api_username,
            sunshine_api_password=sunshine_api_password,
            sunshine_verify_tls=sunshine_verify_tls,
        )

    if job_type == "gaming.connection.revoke":
        payload = job.get("payload") or {}

        if not isinstance(payload, dict):
            return JobExecutionResult(
                "failed",
                {},
                "Gaming connection payload must be an object.",
            )

        return revoke_connection(
            payload,
            state_root=state_root,
            sunshine_api_url=sunshine_api_url,
            sunshine_api_username=sunshine_api_username,
            sunshine_api_password=sunshine_api_password,
            sunshine_verify_tls=sunshine_verify_tls,
        )

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
                vdd_template_path=vdd_template_path,
                vdd_target_root=vdd_target_root,
            )
        action = job_type.rsplit(".", 1)[-1]
        return change_session_state(
            payload,
            state_root=state_root,
            execution_backend=execution_backend,
            streaming_backend=streaming_backend,
            action=action,
            sunshine_api_url=sunshine_api_url,
            sunshine_api_username=sunshine_api_username,
            sunshine_api_password=sunshine_api_password,
            sunshine_verify_tls=sunshine_verify_tls,
        )

    return JobExecutionResult(
        "failed",
        {},
        f"Unsupported gaming job type: {job_type or '<empty>'}.",
    )
