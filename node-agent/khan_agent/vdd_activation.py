"""
Khan Cloud Windows VDD live activation.

The runtime-policy engine owns policy persistence and ordering.
This module owns the Windows-specific step required to make a newly
persisted VDD policy visible to the running indirect-display device.

No driver installation or machine reboot is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import platform
import subprocess
import time
from typing import Any, Callable


VDD_INSTANCE_ID = r"ROOT\DISPLAY\0000"
VDD_FRIENDLY_NAME = "Khan Virtual Display"


class VddActivationError(RuntimeError):
    pass


@dataclass(frozen=True)
class VddDeviceHealth:
    instance_id: str
    status: str
    problem_code: int
    friendly_name: str

    @property
    def healthy(self) -> bool:
        return (
            self.status.strip().upper() == "OK"
            and self.problem_code == 0
        )


Runner = Callable[..., subprocess.CompletedProcess[str]]


def live_activation_available() -> bool:
    """
    Return True only when the current node can execute the Windows
    PnP activation path.

    Runtime-policy rendering/persistence is intentionally platform
    neutral so Linux CI and control-plane tests can validate the same
    policy contract without pretending that Windows PnP exists.
    """
    return platform.system() == "Windows"


def _require_windows() -> None:
    if not live_activation_available():
        raise VddActivationError(
            "VDD live activation requires Windows."
        )


def _powershell(
    script: str,
    *,
    runner: Runner = subprocess.run,
    timeout: float = 30.0,
) -> str:
    _require_windows()

    try:
        result = runner(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VddActivationError(
            f"Windows VDD command failed: {exc}"
        ) from exc

    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"exit code {result.returncode}"
        )
        raise VddActivationError(detail)

    return result.stdout.strip()


def query_vdd_health(
    *,
    runner: Runner = subprocess.run,
) -> VddDeviceHealth:
    script = rf"""
$ErrorActionPreference = 'Stop'

$d = Get-PnpDevice -InstanceId '{VDD_INSTANCE_ID}' `
    -ErrorAction Stop

$problem = 0

try {{
    $p = Get-PnpDeviceProperty `
        -InstanceId '{VDD_INSTANCE_ID}' `
        -KeyName 'DEVPKEY_Device_ProblemCode' `
        -ErrorAction Stop

    if ($null -ne $p.Data) {{
        $problem = [int]$p.Data
    }}
}} catch {{
    $problem = 0
}}

[pscustomobject]@{{
    instance_id   = $d.InstanceId
    status        = [string]$d.Status
    problem_code  = $problem
    friendly_name = [string]$d.FriendlyName
}} | ConvertTo-Json -Compress
"""

    raw = _powershell(script, runner=runner)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VddActivationError(
            "Unable to parse VDD health response."
        ) from exc

    return VddDeviceHealth(
        instance_id=str(payload.get("instance_id") or ""),
        status=str(payload.get("status") or ""),
        problem_code=int(payload.get("problem_code") or 0),
        friendly_name=str(payload.get("friendly_name") or ""),
    )


def restart_vdd_device(
    *,
    runner: Runner = subprocess.run,
    timeout: float = 45.0,
) -> dict[str, Any]:
    """
    Restart only ROOT\\DISPLAY\\0000.

    Execute pnputil directly rather than nesting it beneath
    PowerShell Start-Process. This keeps the restart operation
    bounded by the caller-owned subprocess timeout and leaves
    post-restart recovery to wait_for_vdd_health().

    No reboot is requested.
    """
    _require_windows()

    before = query_vdd_health(runner=runner)

    if not before.healthy:
        raise VddActivationError(
            "Refusing VDD restart because the device "
            f"is unhealthy: status={before.status}, "
            f"problem_code={before.problem_code}"
        )

    command = [
        "pnputil.exe",
        "/restart-device",
        VDD_INSTANCE_ID,
    ]

    started = time.monotonic()

    try:
        result = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise VddActivationError(
            "Khan VDD restart timed out after "
            f"{timeout:.1f} seconds."
        ) from exc
    except OSError as exc:
        raise VddActivationError(
            f"Unable to execute pnputil VDD restart: {exc}"
        ) from exc

    elapsed_ms = round(
        (time.monotonic() - started) * 1000,
        2,
    )

    if result.returncode != 0:
        detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"exit code {result.returncode}"
        )

        raise VddActivationError(
            "pnputil /restart-device failed: "
            f"{detail}"
        )

    return {
        "instance_id": VDD_INSTANCE_ID,
        "exit_code": result.returncode,
        "elapsed_ms": elapsed_ms,
    }


def wait_for_vdd_health(
    *,
    runner: Runner = subprocess.run,
    timeout: float = 20.0,
    interval: float = 0.25,
) -> VddDeviceHealth:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            health = query_vdd_health(runner=runner)
            if health.healthy:
                return health
        except VddActivationError as exc:
            last_error = exc

        time.sleep(interval)

    if last_error is not None:
        raise VddActivationError(
            f"VDD did not recover after activation: {last_error}"
        )

    raise VddActivationError(
        "VDD did not become healthy before activation timeout."
    )


def activate_vdd_policy(
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """
    Verify the live Khan VDD after a runtime-policy update.

    A healthy, started VDD must not be restarted merely to prove
    readiness. The explicit restart_vdd_device() primitive remains
    available for controlled maintenance/recovery paths, but normal
    gaming runtime activation is health-verification only.

    This avoids destabilizing an already healthy UMDF display device
    during customer runtime admission.
    """
    health = query_vdd_health(runner=runner)

    if not health.healthy:
        raise VddActivationError(
            "Refusing VDD activation because the device "
            "is unhealthy: "
            f"status={health.status}, "
            f"problem_code={health.problem_code}"
        )

    return {
        "activation_required": False,
        "activation_method": "health-verification-only",
        "reason": "healthy-vdd-no-pnp-restart",
        "instance_id": health.instance_id,
        "pre_status": health.status,
        "pre_problem_code": health.problem_code,
        "post_status": health.status,
        "post_problem_code": health.problem_code,
        "restart_elapsed_ms": None,
        "healthy": health.healthy,
        "reboot_required": False,
    }
