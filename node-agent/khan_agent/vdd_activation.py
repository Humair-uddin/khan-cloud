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

    pnputil is preferred because it is part of Windows and avoids
    introducing a DevCon dependency. No reboot is requested.
    """
    script = rf"""
$ErrorActionPreference = 'Stop'

$instance = '{VDD_INSTANCE_ID}'

$d = Get-PnpDevice -InstanceId $instance -ErrorAction Stop

if ($d.Status -ne 'OK') {{
    throw "Khan VDD is not healthy before restart: $($d.Status)"
}}

$p = Start-Process `
    -FilePath "$env:SystemRoot\System32\pnputil.exe" `
    -ArgumentList @('/restart-device', $instance) `
    -Wait `
    -PassThru `
    -NoNewWindow

if ($p.ExitCode -ne 0) {{
    throw "pnputil /restart-device failed with exit code $($p.ExitCode)"
}}

[pscustomobject]@{{
    instance_id = $instance
    exit_code   = $p.ExitCode
}} | ConvertTo-Json -Compress
"""

    started = time.monotonic()
    raw = _powershell(
        script,
        runner=runner,
        timeout=timeout,
    )
    elapsed_ms = round(
        (time.monotonic() - started) * 1000,
        2,
    )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VddActivationError(
            "Unable to parse VDD restart response."
        ) from exc

    return {
        "instance_id": str(
            payload.get("instance_id") or ""
        ),
        "exit_code": int(payload.get("exit_code") or 0),
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
    before = query_vdd_health(runner=runner)

    if not before.healthy:
        raise VddActivationError(
            "Refusing VDD activation because the device "
            f"is unhealthy before restart: "
            f"status={before.status}, "
            f"problem_code={before.problem_code}"
        )

    restart = restart_vdd_device(runner=runner)
    after = wait_for_vdd_health(runner=runner)

    return {
        "activation_required": True,
        "activation_method": "pnputil-restart-device",
        "instance_id": after.instance_id,
        "pre_status": before.status,
        "pre_problem_code": before.problem_code,
        "post_status": after.status,
        "post_problem_code": after.problem_code,
        "restart_elapsed_ms": restart["elapsed_ms"],
        "healthy": after.healthy,
        "reboot_required": False,
    }
