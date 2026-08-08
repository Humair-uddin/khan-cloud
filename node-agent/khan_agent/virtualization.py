from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from khan_agent.inventory import _virtualization_inventory


@dataclass(frozen=True)
class JobExecutionResult:
    status: str
    result: dict[str, Any]
    error_message: str = ""


def execute_virtualization_job(job: dict[str, Any], *, execution_enabled: bool) -> JobExecutionResult:
    job_type = str(job.get("job_type", ""))
    if not job_type.startswith("vps."):
        return JobExecutionResult("failed", {}, "Unsupported node job type.")

    capability = _virtualization_inventory()
    if not execution_enabled:
        return JobExecutionResult(
            "blocked",
            {"virtualization": capability},
            "VPS execution is disabled by node policy.",
        )
    if not capability.get("kvm_available") or not capability.get("libvirt_available"):
        return JobExecutionResult(
            "blocked",
            {"virtualization": capability},
            "KVM/libvirt are not ready on this node.",
        )

    # Execution contract is intentionally gated. The next KVM activation epic
    # supplies the libvirt driver after storage/network pools are explicitly configured.
    return JobExecutionResult(
        "blocked",
        {"virtualization": capability},
        "KVM driver activation is not yet enabled for this host.",
    )
