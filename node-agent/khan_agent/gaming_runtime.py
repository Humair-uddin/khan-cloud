from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime

import json
import os
import platform
import signal
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID

from khan_agent.file_security import secure_private_file
from khan_agent.gaming_backends import locate_sunshine, probe_nvidia_gpu
from khan_agent.launch_diagnostics import LaunchTrace
from khan_agent.gaming_launchers import (
    GameLaunchError,
    build_prepared_launch_attempt_authority,
    dispatch_prepared_game,
    launch_prepared_game,
    prepare_game_launch,
)
from khan_agent.sunshine_broker import (
    SunshineBrokerError,
    pair_client,
    probe_sunshine_readiness,
    unpair_client,
)
from khan_agent.windows_workload_observer import (
    WindowsWorkloadObserverError,
    adopt_customer_workload,
    discover_customer_workload_processes,
    make_workload_observation_authority,
)
from khan_agent.windows_verified_process import (
    WindowsVerifiedProcessError,
    inspect_verified_process_ownership,
    snapshot_game_processes,
)
from khan_agent.runtime_ownership import (
    OWNERSHIP_SCHEMA_VERSION,
    RuntimeOwnershipError,
    inspect_runtime_ownership,
    no_process_ownership,
    planned_runtime_ownership,
    terminate_runtime_ownership,
)
from khan_agent.vdd_activation import (
    VddActivationError,
    activate_vdd_policy,
    live_activation_available,
)
from khan_agent.vdd_runtime_policy import (
    VddRuntimePolicyError,
    apply_display_policy,
)
from khan_agent.virtualization import JobExecutionResult
from khan_agent.windows_session_broker import (
    WindowsSessionBrokerError,
    require_interactive_session,
)


class GamingRuntimeError(RuntimeError):
    pass


def _recorded_launcher_pid(state: dict[str, Any]) -> int | None:
    launch_info = state.get("launch_info")
    if not isinstance(launch_info, dict):
        return None
    try:
        pid = int(launch_info.get("launcher_pid"))
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _cleanup_failed_launch(
    runtime_ownership: dict[str, Any],
) -> dict[str, Any]:
    """Terminate a newly launched runtime and prove it is clean."""
    try:
        proof = terminate_runtime_ownership(
            runtime_ownership
        )
    except Exception as exc:
        return {
            "verified": False,
            "runtime_ownership": dict(
                runtime_ownership
            ),
            "termination_proof": None,
            "error": str(exc),
        }

    remaining = int(
        proof.get(
            "owned_process_count_remaining",
            proof.get(
                "owned_process_count",
                0,
            ),
        )
        or 0
    )

    verified = (
        bool(
            proof.get(
                "ownership_boundary_verified"
            )
        )
        and bool(
            proof.get(
                "termination_verified"
            )
        )
        and remaining == 0
    )

    return {
        "verified": verified,
        "runtime_ownership": dict(
            runtime_ownership
        ),
        "termination_proof": proof,
        "error": (
            None
            if verified
            else
            "runtime_termination_not_verified"
        ),
    }


def _process_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _legacy_state_sha256(state_file: Path) -> str:
    return hashlib.sha256(state_file.read_bytes()).hexdigest().upper()


def _legacy_windows_process_snapshot() -> list[dict[str, Any]]:
    if os.name != "nt":
        raise GamingRuntimeError(
            "Legacy retirement currently requires Windows process evidence."
        )

    script = r"""
$ErrorActionPreference = 'Stop'
$items = Get-CimInstance Win32_Process | ForEach-Object {
    [PSCustomObject]@{
        pid = [int]$_.ProcessId
        name = [string]$_.Name
        executable_path = [string]$_.ExecutablePath
        command_line = [string]$_.CommandLine
        creation_date = $(if ($_.CreationDate) {
            $_.CreationDate.ToUniversalTime().ToString("o")
        } else {
            ""
        })
    }
}
@($items) | ConvertTo-Json -Compress -Depth 4
"""
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise GamingRuntimeError(
            "Unable to collect Windows process evidence for "
            "legacy retirement."
        )

    raw = (completed.stdout or "").strip()
    if not raw:
        return []

    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [p for p in parsed if isinstance(p, dict)]
    raise GamingRuntimeError(
        "Windows process evidence returned an invalid payload."
    )


def _legacy_retirement_evidence(
    *,
    payload: dict[str, Any],
    state: dict[str, Any],
    state_file: Path,
    runtime_id: str,
) -> dict[str, Any]:
    expected_sha = str(
        payload.get(
            "legacy_retirement_expected_state_sha256"
        )
        or ""
    ).upper()
    actual_sha = _legacy_state_sha256(state_file)

    if not expected_sha or actual_sha != expected_sha:
        raise GamingRuntimeError(
            "Legacy retirement state hash does not match "
            "operator-authorized evidence."
        )

    expected_runtime = str(
        payload.get("legacy_runtime_id")
        or ""
    )
    if expected_runtime != runtime_id:
        raise GamingRuntimeError(
            "Legacy retirement runtime identity does not match "
            "the operator-authorized runtime."
        )

    schema_version = int(
        state.get("schema_version")
        or state.get("ownership_schema_version")
        or 1
    )
    if schema_version >= 2:
        raise GamingRuntimeError(
            "Legacy retirement is forbidden for D1/V2 runtime state."
        )

    processes = _legacy_windows_process_snapshot()

    game = state.get("game")
    game = game if isinstance(game, dict) else {}
    install_path = str(
        game.get("install_path")
        or ""
    ).strip()

    install_norm = os.path.normcase(
        os.path.normpath(install_path)
    ) if install_path else ""

    game_processes: list[dict[str, Any]] = []
    for proc in processes:
        exe = str(proc.get("executable_path") or "").strip()
        if not exe or not install_norm:
            continue
        exe_norm = os.path.normcase(os.path.normpath(exe))
        try:
            common = os.path.commonpath(
                [install_norm, exe_norm]
            )
        except ValueError:
            continue
        if common == install_norm:
            game_processes.append(proc)

    if game_processes:
        raise GamingRuntimeError(
            "Legacy retirement blocked because a process is still "
            "executing from the recorded game installation."
        )

    supervisor_matches = [
        p for p in processes
        if "windows_job_supervisor" in str(
            p.get("command_line") or ""
        ).lower()
        and runtime_id.lower() in str(
            p.get("command_line") or ""
        ).lower()
    ]
    if supervisor_matches:
        raise GamingRuntimeError(
            "Legacy retirement blocked because a D1 supervisor "
            "still references this runtime."
        )

    launcher_pid = _recorded_launcher_pid(state)
    launcher_proc = next(
        (
            p for p in processes
            if int(p.get("pid") or 0)
            == int(launcher_pid or 0)
        ),
        None,
    )

    recorded_launcher_alive = launcher_proc is not None
    recorded_pid_identity_reused = False

    started_raw = str(
        payload.get("legacy_runtime_started_at")
        or ""
    ).strip()

    if launcher_proc is not None:
        if not started_raw:
            raise GamingRuntimeError(
                "Legacy retirement cannot prove identity of the "
                "currently reused recorded PID without the original "
                "runtime start time."
            )

        try:
            original_started = datetime.fromisoformat(
                started_raw.replace("Z", "+00:00")
            )
            current_created = datetime.fromisoformat(
                str(
                    launcher_proc.get("creation_date")
                    or ""
                ).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise GamingRuntimeError(
                "Legacy retirement process creation evidence "
                "could not be parsed."
            ) from exc

        recorded_pid_identity_reused = (
            current_created > original_started
        )

        if not recorded_pid_identity_reused:
            raise GamingRuntimeError(
                "Legacy retirement cannot prove that the recorded "
                "launcher PID belongs to a later unrelated process."
            )

    return {
        "mode": "legacy_schema_v1_retirement",
        "operator_authorized_job": True,
        "state_sha256": actual_sha,
        "runtime_id": runtime_id,
        "recorded_launcher_pid": launcher_pid,
        "recorded_launcher_alive": recorded_launcher_alive,
        "recorded_pid_identity_reused":
            recorded_pid_identity_reused,
        "recorded_pid_process": (
            launcher_proc or {}
        ),
        "game_install_path": install_path,
        "game_process_count": len(game_processes),
        "supervisor_process_count":
            len(supervisor_matches),
        "destructive_pid_termination_performed": False,
    }


def _terminate_recorded_launcher(pid: int | None) -> bool:
    """Target only the launcher PID recorded for this gaming session.

    C5 deliberately does not enumerate or kill unrelated processes by name.
    """
    if pid is None or not _process_alive(pid):
        return True

    if platform.system() == "Windows":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=15,
        )
        if completed.returncode not in {0, 128} and _process_alive(pid):
            return False
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        except OSError:
            return False

    return not _process_alive(pid)


@dataclass(frozen=True)
class GamingRuntimePaths:
    root: Path

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    def session_file(self, runtime_id: str) -> Path:
        return self.sessions_dir / f"{runtime_id}.json"


def _runtime_id(session_id: str) -> str:
    try:
        normalized = str(UUID(str(session_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise GamingRuntimeError("gaming session_id must be a valid UUID.") from exc
    return f"kc-gaming-{normalized}"


def _state_paths(state_root: Path, session_id: str) -> tuple[GamingRuntimePaths, str, Path]:
    paths = GamingRuntimePaths(Path(state_root))
    runtime_id = _runtime_id(session_id)
    return paths, runtime_id, paths.session_file(runtime_id)


def _read_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GamingRuntimeError(f"Gaming runtime state is unreadable: {path}") from exc
    if not isinstance(raw, dict):
        raise GamingRuntimeError("Gaming runtime state is invalid.")
    return raw


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")

    body = (
        json.dumps(
            state,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    with temp.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())

    secure_private_file(temp)
    os.replace(temp, path)
    secure_private_file(path)

    # POSIX directory fsync makes the rename itself durable across
    # abrupt host loss. Windows FlushFileBuffers semantics are already
    # represented by the file fsync above.
    if platform.system() != "Windows":
        directory_fd = os.open(
            path.parent,
            os.O_RDONLY,
        )

        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def _interactive_session_context() -> dict[str, Any]:
    """
    Validate the Windows desktop execution boundary immediately before
    customer runtime preparation.

    The control plane already rejects nodes whose heartbeat reports no
    interactive session. This is the authoritative node-local recheck,
    protecting against logout/session loss between scheduling and job
    execution.

    Linux unit tests may exercise Windows runtime logic with mocked
    backends, so non-Windows hosts report a deferred validation rather
    than pretending a Windows console exists.
    """
    if platform.system() != "Windows":
        return {
            "required": True,
            "validated": False,
            "reason": "non_windows_test_environment",
        }

    try:
        broker_session = require_interactive_session(
            require_managed=True,
        )
        session_id = int(broker_session.session_id)
    except WindowsSessionBrokerError as exc:
        raise GamingRuntimeError(
            "Windows interactive session is unavailable: "
            f"{exc}"
        ) from exc

    # Session 0 is the Windows services isolation session and must never
    # be used for customer game/UI execution.
    if session_id <= 0:
        raise GamingRuntimeError(
            "Gaming runtime requires a non-zero interactive "
            "Windows user session; session 0 is not permitted."
        )

    return {
        "required": True,
        "validated": True,
        "session_id": session_id,
        "execution_context": "interactive_user",
    }


def _establish_presentation_contract(
    interactive_session: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed on Windows unless Session-1 VDD is 1:1 before launch."""
    if platform.system() != "Windows":
        return {
            "required": True,
            "verified": False,
            "reason": "non_windows_test_environment",
            "requested_mode": {
                "width": 1920,
                "height": 1080,
                "refresh_hz": 60,
            },
        }

    session_id = int(
        interactive_session.get("session_id") or 0
    )

    if (
        not interactive_session.get("validated")
        or session_id <= 0
    ):
        raise GamingRuntimeError(
            "A validated managed Windows session is required "
            "before establishing the VDD presentation contract."
        )

    try:
        from khan_agent.windows_presentation import (
            establish_vdd_presentation_contract,
        )

        return establish_vdd_presentation_contract(
            expected_session_id=session_id,
            width=1920,
            height=1080,
            refresh_hz=60,
        )
    except Exception as exc:
        raise GamingRuntimeError(
            "Pre-launch VDD presentation contract failed: "
            f"{exc}"
        ) from exc


def _connection_info(runtime_id: str) -> dict[str, Any]:
    # Endpoint/credentials are intentionally not invented here. Secure,
    # short-lived customer connection credentials belong to the control-plane
    # connection-broker epic. Runtime V1 reports only verified local readiness.
    return {
        "runtime_id": runtime_id,
        "streaming_backend": "sunshine",
        "protocol": "moonlight",
        "ready": True,
        "credential_mode": "control_plane_pending",
    }


def _validate_windows_native(
    *,
    gpu_uuid: str,
    minimum_vram_mb: int,
    execution_backend: str,
    streaming_backend: str,
) -> dict[str, Any]:
    if execution_backend.strip().lower() != "windows_native":
        raise GamingRuntimeError(
            "Gaming Runtime V1 supports only windows_native execution."
        )
    if streaming_backend.strip().lower() != "sunshine":
        raise GamingRuntimeError(
            "Gaming Runtime V1 requires the Sunshine streaming backend."
        )
    sunshine = locate_sunshine()
    if sunshine is None:
        raise GamingRuntimeError(
            "Sunshine is not available; Khan Cloud will not install or replace it automatically."
        )
    gpu = probe_nvidia_gpu(gpu_uuid)
    if not gpu.get("available"):
        raise GamingRuntimeError(
            "Assigned NVIDIA GPU is not operational or no longer present."
        )
    actual_vram = int(gpu.get("memory_total_mib") or 0)
    if actual_vram < minimum_vram_mb:
        raise GamingRuntimeError(
            f"Assigned GPU has {actual_vram} MiB VRAM; {minimum_vram_mb} MiB is required."
        )
    return {
        "gpu": gpu,
        "sunshine_executable": str(sunshine),
    }


def _display_policy_payload(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    raw = payload.get("display_policy")

    if raw is None:
        return None

    if not isinstance(raw, dict):
        raise GamingRuntimeError(
            "display_policy must be an object."
        )

    # Copy through JSON so the runtime state owns an immutable,
    # plain-data representation independent from caller mutation.
    try:
        normalized = json.loads(
            json.dumps(
                raw,
                sort_keys=True,
            )
        )
    except (TypeError, ValueError) as exc:
        raise GamingRuntimeError(
            "display_policy must contain JSON-compatible values."
        ) from exc

    if not isinstance(normalized, dict):
        raise GamingRuntimeError(
            "display_policy must be an object."
        )

    return normalized


def _validate_existing_display_policy_binding(
    *,
    existing: dict[str, Any],
    requested: dict[str, Any] | None,
) -> None:
    existing_request = existing.get(
        "display_policy_request"
    )

    if existing_request is None:
        if requested is not None:
            raise GamingRuntimeError(
                "Existing gaming runtime was created without "
                "a display policy; refusing policy mutation "
                "through idempotent create."
            )
        return

    if requested is None:
        raise GamingRuntimeError(
            "Existing gaming runtime is bound to a display "
            "policy; idempotent create must include the same "
            "display_policy."
        )

    if existing_request != requested:
        raise GamingRuntimeError(
            "Existing gaming runtime is bound to a different "
            "display policy; refusing policy reassignment."
        )


def _apply_session_display_policy(
    policy_payload: dict[str, Any],
    *,
    template_path: Path,
    target_root: Path,
) -> dict[str, Any]:
    """
    Persist the requested VDD policy and activate it on Windows.

    Ordered idempotent replays are side-effect free: the policy engine
    proves that the active settings already match the persisted state,
    so the VDD must not be restarted again.
    """

    try:
        result = apply_display_policy(
            policy_payload,
            template_path=template_path,
            target_root=target_root,
        )
    except VddRuntimePolicyError as exc:
        raise GamingRuntimeError(
            f"VDD display policy rejected: {exc}"
        ) from exc

    if result.get("idempotent"):
        result["activation"] = {
            "activation_required": False,
            "reason": "idempotent-policy-replay",
            "reboot_required": False,
        }
        return result

    if not live_activation_available():
        result["activation"] = {
            "activation_required": False,
            "activation_available": False,
            "reason": "windows-live-activation-unavailable",
            "reboot_required": False,
        }
        return result

    try:
        result["activation"] = (
            activate_vdd_policy()
        )
    except VddActivationError as exc:
        raise GamingRuntimeError(
            "VDD policy persisted but live activation failed: "
            f"{exc}"
        ) from exc

    return result




def _prepared_workload_observation(
    *,
    runtime_id: str,
    prepared_launch: Any,
    interactive_session: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a clean customer-PLAY observation boundary.

    Commercial session readiness must never silently adopt a process that
    existed before the READY boundary.  The initial snapshot is persisted
    as the observation baseline.  A later customer PLAY must produce an
    identity absent from that baseline.
    """
    if prepared_launch is None:
        return None

    expected_session_id = interactive_session.get("session_id")
    if expected_session_id is None:
        raise GamingRuntimeError(
            "Managed gaming session has no verified Windows session ID."
        )

    game = getattr(prepared_launch, "game", None)
    if not isinstance(game, dict):
        raise GamingRuntimeError(
            "Prepared game metadata is missing."
        )

    install_root = str(
        game.get("install_path") or ""
    ).strip()
    if not install_root:
        raise GamingRuntimeError(
            "Prepared game has no verified install root."
        )

    try:
        baseline = snapshot_game_processes(
            install_root=install_root,
            expected_session_id=int(expected_session_id),
        )
    except WindowsVerifiedProcessError as exc:
        raise GamingRuntimeError(
            "Customer workload observation baseline could not be "
            f"established: {exc}"
        ) from exc

    if baseline:
        raise GamingRuntimeError(
            "Assigned game already has a process in the managed "
            "session before stream readiness; refusing to arm "
            "customer workload observation over a stale process."
        )

    authority = make_workload_observation_authority(
        runtime_id=runtime_id,
        install_root=install_root,
        expected_session_id=int(expected_session_id),
        launcher_type=str(
            getattr(prepared_launch, "launcher_type", "") or ""
        ),
        launcher_game_id=str(
            getattr(prepared_launch, "launcher_game_id", "") or ""
        ),
        baseline=baseline,
    )

    return {
        "schema_version": 1,
        "generation": 1,
        "state": "armed",
        "authority": authority,
        "last_observed_processes": [],
    }


def _rearm_customer_workload(
    state: dict[str, Any],
) -> dict[str, Any]:
    observation = state.get("workload_observation")
    if not isinstance(observation, dict):
        raise GamingRuntimeError(
            "Running resource session has no workload observation state."
        )

    authority = observation.get("authority")
    if not isinstance(authority, dict):
        raise GamingRuntimeError(
            "Workload observation authority is missing."
        )

    install_root = str(authority.get("install_root") or "").strip()
    expected_session_id = authority.get(
        "interactive_session_id"
    )

    if not install_root or expected_session_id is None:
        raise GamingRuntimeError(
            "Workload observation authority is incomplete."
        )

    try:
        baseline = snapshot_game_processes(
            install_root=install_root,
            expected_session_id=int(expected_session_id),
        )
    except WindowsVerifiedProcessError as exc:
        raise GamingRuntimeError(
            f"Workload observation could not be re-armed: {exc}"
        ) from exc

    if baseline:
        raise GamingRuntimeError(
            "Cannot re-arm workload observation while an unowned "
            "assigned-game process is present."
        )

    generation = int(observation.get("generation") or 1) + 1

    new_authority = make_workload_observation_authority(
        runtime_id=str(authority.get("runtime_id") or ""),
        install_root=install_root,
        expected_session_id=int(expected_session_id),
        launcher_type=str(authority.get("launcher_type") or ""),
        launcher_game_id=str(
            authority.get("launcher_game_id") or ""
        ),
        baseline=baseline,
    )

    return {
        "schema_version": 1,
        "generation": generation,
        "state": "armed",
        "authority": new_authority,
        "last_observed_processes": [],
    }


def _reconcile_customer_workload_state(
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Observe/adopt/retire customer-launched game workload.

    This function never starts a game and never changes commercial billing.
    """
    observation = state.get("workload_observation")
    if not isinstance(observation, dict):
        return state, {
            "changed": False,
            "state": "not_configured",
        }

    ownership = state.get("runtime_ownership")
    if not isinstance(ownership, dict):
        raise GamingRuntimeError(
            "Runtime ownership metadata is missing."
        )

    ownership_type = str(
        ownership.get("ownership_type") or ""
    )

    # Armed: detect only identities newer than the persisted baseline.
    if ownership_type == "none":
        if observation.get("state") != "armed":
            raise GamingRuntimeError(
                "Workload observation generation is not armed."
            )

        authority = observation.get("authority")
        if not isinstance(authority, dict):
            raise GamingRuntimeError(
                "Workload observation authority is missing."
            )

        try:
            discovered = discover_customer_workload_processes(
                authority
            )
        except WindowsWorkloadObserverError as exc:
            raise GamingRuntimeError(
                f"Customer workload observation failed: {exc}"
            ) from exc

        if not discovered:
            observation["state"] = "armed"
            state["workload_observation"] = observation
            return state, {
                "changed": False,
                "state": "armed",
                "generation": int(
                    observation.get("generation") or 1
                ),
            }

        try:
            adopted = adopt_customer_workload(
                authority,
                discovered,
            )
        except WindowsWorkloadObserverError as exc:
            raise GamingRuntimeError(
                f"Customer workload adoption failed: {exc}"
            ) from exc

        state["runtime_ownership"] = adopted
        observation["state"] = "running"
        observation["last_observed_processes"] = discovered
        state["workload_observation"] = observation

        workload_launch = state.get("workload_launch")
        if isinstance(workload_launch, dict):
            state["last_play"] = {
                "node_job_id": str(
                    workload_launch.get("node_job_id") or ""
                ),
                "attempt_id": str(
                    workload_launch.get("attempt_id") or ""
                ),
                "generation": int(
                    observation.get("generation") or 1
                ),
                "state": "observed",
            }
            state.pop("launch_attempt", None)
            state.pop("workload_launch", None)
            state.pop("launch_failure", None)

        return state, {
            "changed": True,
            "state": "running",
            "generation": int(
                observation.get("generation") or 1
            ),
            "owned_process_count": len(discovered),
        }

    # Adopted D1 workload: inspect exact persisted identities.
    if ownership_type == "windows_verified_process":
        try:
            proof = inspect_verified_process_ownership(
                ownership
            )
        except WindowsVerifiedProcessError as exc:
            raise GamingRuntimeError(
                f"Customer workload ownership inspection failed: {exc}"
            ) from exc

        remaining = int(
            proof.get(
                "owned_process_count_remaining",
                proof.get("owned_process_count", 0),
            )
            or 0
        )

        if remaining > 0:
            observation["state"] = "running"
            state["workload_observation"] = observation
            return state, {
                "changed": False,
                "state": "running",
                "generation": int(
                    observation.get("generation") or 1
                ),
                "owned_process_count": remaining,
            }

        if not bool(
            proof.get("ownership_boundary_verified")
        ):
            raise GamingRuntimeError(
                "Retired customer workload ownership boundary "
                "could not be verified."
            )

        # Exact D1 generation is retired. Commercial session remains
        # running; arm the next customer PLAY generation.
        state["runtime_ownership"] = no_process_ownership()
        state["workload_observation"] = (
            _rearm_customer_workload(state)
        )

        return state, {
            "changed": True,
            "state": "armed",
            "generation": int(
                state["workload_observation"]["generation"]
            ),
            "previous_generation_retired": True,
        }

    raise GamingRuntimeError(
        "Running resource session has unsupported workload ownership "
        f"type: {ownership_type!r}"
    )



def play_customer_workload(
    payload: dict[str, Any],
    *,
    state_root: Path,
    node_job_id: str,
) -> JobExecutionResult:
    """Dispatch one customer PLAY inside an existing commercial session."""

    session_id = str(payload.get("session_id") or "").strip()
    if not session_id:
        return JobExecutionResult(
            "failed",
            {},
            "PLAY requires session_id.",
        )

    try:
        normalized_job_id = str(UUID(str(node_job_id))).lower()
    except (TypeError, ValueError, AttributeError):
        return JobExecutionResult(
            "failed",
            {},
            "PLAY requires an authoritative node job ID.",
        )

    forbidden_launch_fields = {
        "executable",
        "launcher_executable",
        "install_path",
        "install_root",
        "app_id",
    }
    supplied_forbidden = sorted(
        forbidden_launch_fields.intersection(payload)
    )
    if supplied_forbidden:
        return JobExecutionResult(
            "failed",
            {},
            "PLAY payload contains forbidden launch fields: "
            + ", ".join(supplied_forbidden),
        )

    try:
        _, runtime_id, state_file = _state_paths(
            state_root,
            session_id,
        )

        state = _read_state(state_file)
        if not isinstance(state, dict):
            raise GamingRuntimeError(
                "PLAY runtime state does not exist."
            )

        if str(state.get("runtime_id") or "") != runtime_id:
            raise GamingRuntimeError(
                "PLAY runtime identity mismatch."
            )

        requested_runtime_id = str(
            payload.get("runtime_id") or ""
        ).strip()

        if requested_runtime_id != runtime_id:
            raise GamingRuntimeError(
                "PLAY requested a different runtime."
            )

        if state.get("status") != "running":
            raise GamingRuntimeError(
                "PLAY requires a running commercial runtime."
            )

        if state.get("runtime_stage") != "stream_ready":
            raise GamingRuntimeError(
                "PLAY requires stream_ready."
            )

        if not str(payload.get("gaming_title_id") or "").strip():
            raise GamingRuntimeError(
                "PLAY requires server-assigned title identity."
            )

        persisted_identity = {
            "game_slug": str(state.get("game_slug") or "").strip(),
            "launcher_type": str(
                state.get("launcher_type")
                or state.get("launcher")
                or ""
            ).strip().lower(),
            "launcher_game_id": str(
                state.get("launcher_game_id")
                or state.get("launcher_app_id")
                or ""
            ).strip(),
        }
        for key, persisted_value in persisted_identity.items():
            requested_value = str(payload.get(key) or "").strip()
            if key == "launcher_type":
                requested_value = requested_value.lower()
            if not persisted_value or requested_value != persisted_value:
                raise GamingRuntimeError(
                    "PLAY server assignment does not match persisted "
                    f"runtime {key}."
                )

        interactive_session = state.get("interactive_session")
        if not isinstance(interactive_session, dict):
            raise GamingRuntimeError(
                "PLAY managed interactive-session authority is missing."
            )
        try:
            expected_session_id = int(
                interactive_session.get("session_id") or 0
            )
        except (TypeError, ValueError):
            expected_session_id = 0
        if (
            interactive_session.get("validated") is not True
            or expected_session_id <= 0
        ):
            raise GamingRuntimeError(
                "PLAY requires a verified managed interactive session."
            )

        # A reclaimed NodeJob that already reached observer adoption is
        # complete. It must not depend on the still-running workload being
        # inspectable before acknowledging the same logical job again.
        last_play = state.get("last_play")
        if (
            isinstance(last_play, dict)
            and str(last_play.get("node_job_id") or "").lower()
            == normalized_job_id
        ):
            return JobExecutionResult(
                "succeeded",
                {
                    "session_id": session_id,
                    "runtime_id": runtime_id,
                    "deployment_stage": "stream_ready",
                    "play_state": str(last_play.get("state") or "observed"),
                    "idempotent": True,
                },
            )

        # Reconcile first so PLAY cannot race a game which appeared
        # after the previous heartbeat.
        state, observation = _reconcile_customer_workload_state(
            state
        )

        if observation.get("changed"):
            _write_state(state_file, state)

        workload = state.get("workload_observation")
        if not isinstance(workload, dict):
            raise GamingRuntimeError(
                "PLAY workload observation authority is missing."
            )
        generation = int(workload.get("generation") or 0)

        launch_attempt = state.get("launch_attempt")
        workload_launch = state.get("workload_launch")
        if isinstance(launch_attempt, dict):
            if not isinstance(workload_launch, dict):
                raise GamingRuntimeError(
                    "PLAY launch-attempt authority has no job binding."
                )
            if (
                str(workload_launch.get("node_job_id") or "").lower()
                == normalized_job_id
            ):
                return JobExecutionResult(
                    "succeeded",
                    {
                        "session_id": session_id,
                        "runtime_id": runtime_id,
                        "deployment_stage": "stream_ready",
                        "play_state": str(
                            workload_launch.get("state") or "dispatch_pending"
                        ),
                        "launch_attempt_id": str(
                            launch_attempt.get("attempt_id") or ""
                        ),
                        "idempotent": True,
                    },
                )
            raise GamingRuntimeError(
                "Another PLAY launch attempt is still pending."
            )
        if isinstance(workload_launch, dict):
            raise GamingRuntimeError(
                "PLAY job binding exists without launch-attempt authority."
            )

        ownership = state.get("runtime_ownership")
        if not isinstance(ownership, dict):
            raise GamingRuntimeError(
                "PLAY runtime ownership authority is missing."
            )

        if str(ownership.get("ownership_type") or "") != "none":
            raise GamingRuntimeError(
                "Assigned workload is already owned/running."
            )

        if workload.get("state") != "armed":
            raise GamingRuntimeError(
                "PLAY workload generation is not armed."
            )

        # START already prepared and persisted the server-authoritative
        # assigned game metadata. Rebuild local launch preparation from
        # that authority; never accept executable/install paths from
        # the customer request.
        launch_payload = {
            "session_id": session_id,
            "runtime_id": runtime_id,
            **persisted_identity,
        }

        prepared = prepare_game_launch(launch_payload)

        if prepared is None:
            raise GamingRuntimeError(
                "Assigned game could not be prepared for PLAY."
            )

        prepared = replace(
            prepared,
            runtime_id=runtime_id,
            expected_session_id=expected_session_id,
            presentation_contract=(
                state.get("presentation_contract")
                if isinstance(state.get("presentation_contract"), dict)
                else None
            ),
        )

        authority = workload.get("authority")
        if not isinstance(authority, dict):
            raise GamingRuntimeError(
                "PLAY observation authority is missing."
            )
        prepared_install_root = str(
            prepared.game.get("install_path") or ""
        ).strip().rstrip("\\/").casefold()
        observed_install_root = str(
            authority.get("install_root") or ""
        ).strip().rstrip("\\/").casefold()
        if (
            not prepared_install_root
            or prepared_install_root != observed_install_root
            or str(authority.get("runtime_id") or "") != runtime_id
            or int(authority.get("interactive_session_id") or 0)
            != expected_session_id
        ):
            raise GamingRuntimeError(
                "PLAY prepared game does not match observation authority."
            )

        launch_attempt = build_prepared_launch_attempt_authority(
            prepared
        )

        if not isinstance(launch_attempt, dict):
            raise GamingRuntimeError(
                "PLAY could not establish durable launch-attempt authority."
            )

        attempt_id = str(
            launch_attempt.get("attempt_id") or ""
        ).strip()
        if not attempt_id:
            raise GamingRuntimeError(
                "PLAY launch-attempt authority has no identity."
            )

        # Crash-idempotence boundary: persist the exact process baseline,
        # session/install authority, logical NodeJob, and generation before
        # the launcher is allowed to create any process.
        state["launch_attempt"] = launch_attempt
        state["workload_launch"] = {
            "node_job_id": normalized_job_id,
            "attempt_id": attempt_id,
            "generation": generation,
            "state": "dispatch_pending",
        }
        state.pop("launch_failure", None)
        _write_state(state_file, state)

        try:
            launch_info = dispatch_prepared_game(
                prepared,
                launch_attempt=launch_attempt,
            )
        except Exception as exc:
            failed_state = _read_state(state_file) or state
            current_attempt = failed_state.get("launch_attempt")
            if (
                isinstance(current_attempt, dict)
                and str(current_attempt.get("attempt_id") or "")
                == attempt_id
            ):
                failed_state["launch_failure"] = {
                    "attempt_id": attempt_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
                failed_state["workload_launch"] = {
                    **dict(failed_state.get("workload_launch") or {}),
                    "state": "dispatch_outcome_unknown",
                }
                _write_state(state_file, failed_state)
            raise

        # Dispatch success is not workload ownership. The observer will
        # discover and adopt the exact post-baseline game asynchronously.
        state = _read_state(state_file)
        if not isinstance(state, dict):
            raise GamingRuntimeError(
                "PLAY runtime state disappeared after dispatch."
            )
        current_attempt = state.get("launch_attempt")
        if (
            not isinstance(current_attempt, dict)
            or str(current_attempt.get("attempt_id") or "") != attempt_id
        ):
            raise GamingRuntimeError(
                "PLAY runtime authority changed during dispatch."
            )

        if isinstance(launch_info, dict):
            state["launch_info"] = launch_info

        state["workload_launch"] = {
            **dict(state.get("workload_launch") or {}),
            "state": "dispatched",
        }

        state["runtime_stage"] = "stream_ready"
        _write_state(state_file, state)

        return JobExecutionResult(
            "succeeded",
            {
                "session_id": session_id,
                "runtime_id": runtime_id,
                "deployment_stage": "stream_ready",
                "game_slug": state.get("game_slug"),
                "play_state": "dispatched",
                "launch_attempt_id": attempt_id,
            },
        )

    except GamingRuntimeError as exc:
        return JobExecutionResult(
            "blocked",
            {},
            str(exc),
        )
    except Exception as exc:
        return JobExecutionResult(
            "failed",
            {},
            f"PLAY failed: {type(exc).__name__}: {exc}",
        )

def reconcile_customer_workloads(
    state_root: Path,
) -> list[dict[str, Any]]:
    """Lightweight recurring reconciliation for customer PLAY/EXIT.

    Unlike startup recovery reconciliation, this is safe to call on every
    heartbeat.  It does not launch workloads, stop commercial sessions,
    modify billing, or sanitize unrelated processes.
    """
    outcomes: list[dict[str, Any]] = []
    paths = GamingRuntimePaths(Path(state_root))

    if not paths.sessions_dir.exists():
        return outcomes

    for state_file in sorted(
        paths.sessions_dir.glob("kc-gaming-*.json")
    ):
        state = _read_state(state_file)
        if not isinstance(state, dict):
            continue

        if (
            state.get("status") != "running"
            or state.get("runtime_stage") != "stream_ready"
        ):
            continue

        session_id = str(state.get("session_id") or "")

        try:
            updated, outcome = (
                _reconcile_customer_workload_state(state)
            )

            if outcome.get("changed"):
                _write_state(state_file, updated)

            outcomes.append(
                {
                    "session_id": session_id,
                    **outcome,
                }
            )
        except Exception as exc:
            outcomes.append(
                {
                    "session_id": session_id,
                    "changed": False,
                    "state": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    return outcomes



def create_session(
    payload: dict[str, Any],
    *,
    state_root: Path,
    execution_backend: str,
    streaming_backend: str,
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
    session_id = str(payload.get("session_id") or "")
    gpu_uuid = str(payload.get("gpu_uuid") or "").strip()
    if not gpu_uuid:
        return JobExecutionResult("failed", {}, "gaming.session.create gpu_uuid is required.")
    try:
        minimum_vram_mb = int(payload.get("minimum_vram_mb", 8192))
    except (TypeError, ValueError):
        return JobExecutionResult("failed", {}, "minimum_vram_mb must be an integer.")
    if minimum_vram_mb < 8192:
        return JobExecutionResult("failed", {}, "Gaming hosts require at least 8192 MiB VRAM.")

    try:
        paths, runtime_id, state_file = _state_paths(state_root, session_id)
        trace = LaunchTrace(runtime_id=runtime_id)
        trace.emit("runtime_preparation_begin")

        display_policy_request = _display_policy_payload(
            payload
        )

        existing = _read_state(state_file)

        if existing is not None:
            if str(existing.get("gpu_uuid")) != gpu_uuid:
                raise GamingRuntimeError(
                    "Existing runtime is bound to a different GPU; refusing reassignment."
                )

            _validate_existing_display_policy_binding(
                existing=existing,
                requested=display_policy_request,
            )

            validation = _validate_windows_native(
                gpu_uuid=gpu_uuid,
                minimum_vram_mb=minimum_vram_mb,
                execution_backend=execution_backend,
                streaming_backend=streaming_backend,
            )
            interactive_session = (
                _interactive_session_context()
            )
            existing["interactive_session"] = (
                interactive_session
            )
            # Idempotent create must never resurrect or otherwise
            # mutate an existing session's lifecycle state. A delayed
            # duplicate create can arrive after a legitimate stop.
            existing["gpu"] = validation["gpu"]

            if existing.get("status") == "running":
                ownership = existing.get("runtime_ownership")
                if not isinstance(ownership, dict):
                    raise GamingRuntimeError(
                        "Running runtime has no structural ownership metadata."
                    )

                launch_info = existing.get("launch_info")
                if launch_info is not None and not isinstance(
                    launch_info,
                    dict,
                ):
                    raise GamingRuntimeError(
                        "Running runtime launch metadata is invalid."
                    )

                display_activation = None
                display_policy = existing.get("display_policy")
                if isinstance(display_policy, dict):
                    candidate = display_policy.get("activation")
                    if isinstance(candidate, dict):
                        display_activation = candidate

                try:
                    readiness = _verify_stream_readiness(
                        runtime_id=runtime_id,
                        runtime_ownership=ownership,
                        launch_info=launch_info,
                        display_activation=display_activation,
                        sunshine_api_url=sunshine_api_url,
                        sunshine_api_username=sunshine_api_username,
                        sunshine_api_password=sunshine_api_password,
                        sunshine_verify_tls=sunshine_verify_tls,
                    )
                except Exception:
                    existing.pop(
                        "stream_readiness",
                        None,
                    )
                    existing[
                        "runtime_stage"
                    ] = "readiness_pending"
                    _write_state(
                        state_file,
                        existing,
                    )
                    raise

                existing["stream_readiness"] = readiness
                existing["runtime_stage"] = "stream_ready"

            _write_state(state_file, existing)

            result: dict[str, Any] = {
                "runtime_id": runtime_id,
                "status": str(existing.get("status") or "unknown"),
                "deployment_stage": str(
                    existing.get("runtime_stage")
                    or existing.get("status")
                    or "unknown"
                ),
                "interactive_session": interactive_session,
                "idempotent": True,
            }

            if existing.get("status") == "running":
                result["connection_info"] = _connection_info(runtime_id)
                result["stream_readiness"] = existing[
                    "stream_readiness"
                ]

            if existing.get("display_policy") is not None:
                result["display_policy"] = existing[
                    "display_policy"
                ]

            return JobExecutionResult(
                "succeeded",
                result,
            )

        validation = _validate_windows_native(
            gpu_uuid=gpu_uuid,
            minimum_vram_mb=minimum_vram_mb,
            execution_backend=execution_backend,
            streaming_backend=streaming_backend,
        )
        trace.emit("runtime_validation_end")
        trace.emit("managed_session_validation_begin")

        # KG-009: authoritative last-moment session broker gate.
        # Scheduling heartbeat evidence can become stale after placement;
        # therefore the Windows node verifies the actual console session
        # again before touching VDD state or launching the game.
        interactive_session = (
            _interactive_session_context()
        )
        trace.emit(
            "managed_session_validation_end",
            validated=bool(interactive_session.get("validated")),
        )
        trace.emit("display_prerequisites_begin")

        display_policy_result: dict[str, Any] | None = None

        if display_policy_request is not None:
            display_policy_result = (
                _apply_session_display_policy(
                    display_policy_request,
                    template_path=vdd_template_path,
                    target_root=vdd_target_root,
                )
            )

        presentation_contract = (
            _establish_presentation_contract(
                interactive_session
            )
        )
        trace.emit("display_prerequisites_end")
        trace.emit("steam_inventory_readiness_begin")
        # Display policy is validated and atomically persisted
        # before game preparation or launch. Invalid VDD policy
        # therefore fails closed before customer workload start.
        prepared_launch = prepare_game_launch(payload)
        trace.emit(
            "steam_inventory_readiness_end",
            has_prepared_launch=prepared_launch is not None,
        )
        trace.emit("runtime_preparation_end")

        # Q38IU-Y44C-R2:
        # The assigned game remains part of the commercial session,
        # but customer workload execution is NOT part of resource
        # session START.
        #
        # prepare_game_launch() above has already:
        #   - resolved the requested game identity,
        #   - verified the Steam AppID is installed on this node,
        #   - resolved the installed-game metadata/install path,
        #   - verified that Steam is available.
        #
        # We deliberately do not build launch-attempt authority and
        # do not call launch_prepared_game() here. The customer will
        # authenticate to Steam and press PLAY interactively later.
        # A separate workload-observer lifecycle will adopt/verify
        # that resulting process without controlling GPU billing.
        launch_info: dict[str, Any] | None = None

        if prepared_launch is not None:
            prepared_launch = replace(
                prepared_launch,
                runtime_id=runtime_id,
                expected_session_id=(
                    interactive_session.get("session_id")
                    if interactive_session.get("validated")
                    else None
                ),
                presentation_contract=presentation_contract,
            )

        workload_observation = (
            _prepared_workload_observation(
                runtime_id=runtime_id,
                prepared_launch=prepared_launch,
                interactive_session=interactive_session,
            )
        )

        runtime_ownership = (
            dict(
                launch_info.get(
                    "runtime_ownership"
                ) or {}
            )
            if launch_info is not None
            else no_process_ownership()
        )

        display_activation = None
        if isinstance(display_policy_result, dict):
            candidate = display_policy_result.get("activation")
            if isinstance(candidate, dict):
                display_activation = candidate

        trace.emit("stream_readiness_begin")
        try:
            readiness = _verify_stream_readiness(
                runtime_id=runtime_id,
                runtime_ownership=runtime_ownership,
                launch_info=launch_info,
                display_activation=display_activation,
                sunshine_api_url=sunshine_api_url,
                sunshine_api_username=sunshine_api_username,
                sunshine_api_password=sunshine_api_password,
                sunshine_verify_tls=sunshine_verify_tls,
            )
        except Exception as readiness_exc:
            trace.emit("stream_readiness_end", verified=False,
                       error_type=type(readiness_exc).__name__)
            if launch_info is not None:
                cleanup = _cleanup_failed_launch(
                    runtime_ownership
                )

                if cleanup["verified"]:
                    try:
                        state_file.unlink()
                    except FileNotFoundError:
                        pass
                else:
                    cleanup_state = dict(
                        launching_state
                    )
                    cleanup_state["status"] = (
                        "cleanup_required"
                    )
                    cleanup_state["runtime_stage"] = (
                        "cleanup_required"
                    )
                    cleanup_state[
                        "runtime_ownership"
                    ] = runtime_ownership
                    cleanup_state["launch_info"] = (
                        launch_info
                    )
                    cleanup_state[
                        "readiness_failure"
                    ] = {
                        "type":
                            type(
                                readiness_exc
                            ).__name__,
                        "message":
                            str(readiness_exc),
                    }
                    cleanup_state[
                        "cleanup"
                    ] = cleanup

                    _write_state(
                        state_file,
                        cleanup_state,
                    )

            raise

        trace.emit("stream_readiness_end", verified=True)
        state = {
            "schema_version": 2,
            "session_id": session_id,
            "runtime_id": runtime_id,
            "status": "running",
            "execution_backend": "windows_native",
            "streaming_backend": "sunshine",
            "gpu_uuid": gpu_uuid,
            "gpu": validation["gpu"],
            "minimum_vram_mb": minimum_vram_mb,
            "runtime_stage": "stream_ready",
            "interactive_session": interactive_session,
            "presentation_contract":
                presentation_contract,
            "runtime_ownership": runtime_ownership,
            "stream_readiness": readiness,
        }

        if display_policy_result is not None:
            state["display_policy_request"] = (
                display_policy_request
            )
            state["display_policy"] = (
                display_policy_result
            )

        if prepared_launch is not None:
            # Q38IU-Y44C-R2:
            # Persist the concerned installed game even though no
            # customer game process exists yet.
            state.update(
                {
                    "game_slug":
                        prepared_launch.game_slug,
                    "launcher_type":
                        prepared_launch.launcher_type,
                    "launcher_game_id":
                        prepared_launch.launcher_game_id,
                    # Preserve KG-001 compatibility keys.
                    "launcher":
                        prepared_launch.launcher_type,
                    "launcher_app_id":
                        prepared_launch.launcher_game_id,
                    "game":
                        prepared_launch.game,
                }
            )

        if workload_observation is not None:
            state["workload_observation"] = workload_observation

        if launch_info is not None:
            state["launch_info"] = launch_info

        _write_state(state_file, state)

        result: dict[str, Any] = {
            "runtime_id": runtime_id,
            "deployment_stage": "stream_ready",
            "connection_info":
                _connection_info(runtime_id),
            "gpu": validation["gpu"],
            "interactive_session": interactive_session,
            "presentation_contract":
                presentation_contract,
            "stream_readiness": readiness,
        }

        if display_policy_result is not None:
            result["display_policy"] = (
                display_policy_result
            )

        if prepared_launch is not None:
            result["game"] = prepared_launch.game
            result["game_slug"] = prepared_launch.game_slug
            result["launcher_type"] = (
                prepared_launch.launcher_type
            )
            result["launcher_game_id"] = (
                prepared_launch.launcher_game_id
            )

        if launch_info is not None:
            result["launch_info"] = launch_info

        return JobExecutionResult(
            "succeeded",
            result,
        )
    except (GamingRuntimeError, GameLaunchError) as exc:
        return JobExecutionResult("blocked", {}, str(exc))



def _verified_terminated_ownership(
    ownership: dict[str, Any],
) -> dict[str, Any] | None:
    """Validate persisted terminal ownership evidence.

    A ``terminated`` descriptor is not an active ownership
    mechanism and must never be accepted by stream-readiness
    inspection.  It is durable evidence produced by a successful
    schema-v2 STOP so a later DELETE can prove the already-destroyed
    ownership boundary clean without attempting to terminate it
    again.
    """
    if str(
        ownership.get("ownership_type") or ""
    ) != "terminated":
        return None

    try:
        remaining = int(
            ownership.get(
                "owned_process_count_remaining",
                ownership.get(
                    "owned_process_count",
                    -1,
                ),
            )
        )
    except (TypeError, ValueError):
        return None

    if (
        not bool(
            ownership.get(
                "ownership_boundary_verified"
            )
        )
        or not bool(
            ownership.get(
                "termination_verified"
            )
        )
        or remaining != 0
        or not bool(ownership.get("clean"))
    ):
        return None

    return {
        "ownership_type": "terminated",
        "runtime_id": str(
            ownership.get("runtime_id") or ""
        ),
        "owned_processes_before": [],
        "owned_processes_remaining": [],
        "owned_process_count_before": 0,
        "owned_process_count_remaining": 0,
        "termination_verified": True,
        "ownership_boundary_verified": True,
        "clean": True,
        "already_terminated": True,
    }


def _verify_runtime_ownership_ready(
    ownership: dict[str, Any],
    *,
    require_process: bool,
) -> dict[str, Any]:
    """Prove that the runtime ownership boundary is usable.

    Generic sessions intentionally permit the no-process ownership
    contract. Game-backed sessions require at least one process inside
    the verified D1 ownership boundary.
    """
    try:
        proof = inspect_runtime_ownership(ownership)
    except RuntimeOwnershipError as exc:
        raise GamingRuntimeError(
            "Gaming runtime ownership readiness could not be verified: "
            f"{exc}"
        ) from exc

    if not bool(proof.get("ownership_boundary_verified")):
        raise GamingRuntimeError(
            "Gaming runtime ownership boundary is not verified."
        )

    process_count = int(
        proof.get(
            "owned_process_count",
            proof.get("owned_process_count_remaining", 0),
        )
        or 0
    )

    if require_process and process_count <= 0:
        raise GamingRuntimeError(
            "Gaming workload has no live process inside its verified "
            "runtime ownership boundary."
        )

    return proof


def _verify_stream_readiness(
    *,
    runtime_id: str,
    runtime_ownership: dict[str, Any],
    launch_info: dict[str, Any] | None,
    display_activation: dict[str, Any] | None,
    sunshine_api_url: str,
    sunshine_api_username: str,
    sunshine_api_password: str,
    sunshine_verify_tls: bool,
) -> dict[str, Any]:
    """Build the authoritative D3 stream-readiness proof."""

    if display_activation is not None:
        if not bool(display_activation.get("healthy")):
            raise GamingRuntimeError(
                "Khan VDD did not produce a healthy post-activation "
                "display state."
            )

    try:
        sunshine = probe_sunshine_readiness(
            api_url=sunshine_api_url,
            username=sunshine_api_username,
            password=sunshine_api_password,
            verify_tls=sunshine_verify_tls,
        )
    except SunshineBrokerError as exc:
        raise GamingRuntimeError(
            "Sunshine stream readiness could not be verified: "
            f"{exc}"
        ) from exc

    ownership = _verify_runtime_ownership_ready(
        runtime_ownership,
        require_process=launch_info is not None,
    )

    if launch_info is not None:
        presentation = launch_info.get(
            "presentation"
        )

        if (
            isinstance(presentation, dict)
            and bool(
                presentation.get("required")
            )
            and not bool(
                presentation.get("verified")
            )
        ):
            detail = str(
                presentation.get("error")
                or presentation.get("reason")
                or "presentation verification failed"
            )

            raise GamingRuntimeError(
                "Customer game presentation was not "
                "verified on Khan VDD before stream "
                f"readiness: {detail}"
            )

    launcher_pid = None
    if launch_info is not None:
        try:
            launcher_pid = int(
                launch_info.get("launcher_pid")
            )
        except (TypeError, ValueError):
            launcher_pid = None

        if launcher_pid is None or launcher_pid <= 0:
            raise GamingRuntimeError(
                "Gaming workload launch did not return a valid "
                "launcher process identity."
            )

    return {
        "runtime_id": runtime_id,
        "verified": True,
        "display": {
            "required": display_activation is not None,
            "healthy": (
                bool(display_activation.get("healthy"))
                if display_activation is not None
                else True
            ),
        },
        "sunshine": sunshine,
        "ownership": ownership,
        "launcher_pid": launcher_pid,
        "workload_process_required":
            launch_info is not None,
    }


def change_session_state(
    payload: dict[str, Any],
    *,
    state_root: Path,
    execution_backend: str,
    streaming_backend: str,
    action: str,
    sunshine_api_url: str = "https://127.0.0.1:47990",
    sunshine_api_username: str = "",
    sunshine_api_password: str = "",
    sunshine_verify_tls: bool = False,
) -> JobExecutionResult:
    session_id = str(payload.get("session_id") or "")
    try:
        _, runtime_id, state_file = _state_paths(state_root, session_id)
        trace = LaunchTrace(runtime_id=runtime_id)
        if action == "start":
            trace.emit("runtime_start_enter")
            trace.emit("runtime_preparation_begin")
        state = _read_state(state_file)
        if state is None:
            if (
                action == "delete"
                and payload.get("legacy_retirement")
            ):
                expected_sha = str(
                    payload.get(
                        "legacy_retirement_expected_state_sha256"
                    )
                    or ""
                ).upper()

                if not expected_sha:
                    raise GamingRuntimeError(
                        "Legacy retirement retry is missing the "
                        "operator-authorized state hash."
                    )

                archive_file = state_file.with_name(
                    state_file.name
                    + ".legacy-retired-"
                    + expected_sha
                )

                if not archive_file.exists():
                    raise GamingRuntimeError(
                        "Legacy retirement state and authorized "
                        "archive are both absent; retirement proof "
                        "cannot be reconstructed."
                    )

                archive_sha = hashlib.sha256(
                    archive_file.read_bytes()
                ).hexdigest().upper()

                if archive_sha != expected_sha:
                    raise GamingRuntimeError(
                        "Legacy retirement archive hash does not "
                        "match operator-authorized evidence."
                    )

                archived_state = _read_state(archive_file)
                if archived_state is None:
                    raise GamingRuntimeError(
                        "Legacy retirement archive cannot be read."
                    )

                retirement = _legacy_retirement_evidence(
                    payload=payload,
                    state=archived_state,
                    state_file=archive_file,
                    runtime_id=runtime_id,
                )

                retirement["state_archived"] = True
                retirement["archive_path"] = str(
                    archive_file
                )
                retirement["retry_from_archive"] = True

                launcher_pid = (
                    archived_state.get("launch_info") or {}
                ).get("launcher_pid")

                sanitation = {
                    "sanitized": True,
                    "runtime_state_deleted": True,
                    "paired_clients_remaining": 0,
                    "recorded_launcher_pid":
                        launcher_pid,
                    "recorded_launcher_alive": bool(
                        retirement[
                            "recorded_launcher_alive"
                        ]
                    ),
                    "recorded_launcher_terminated": False,
                    "ownership_schema_version": 1,
                    "runtime_ownership": {
                        "ownership_type":
                            "legacy_operator_retirement",
                        "ownership_boundary_verified": False,
                        "termination_verified": False,
                        "owned_process_count_remaining": 0,
                        "reason":
                            "legacy_runtime_retired_by_evidence",
                    },
                    "legacy_retirement": retirement,
                }

                return JobExecutionResult(
                    "succeeded",
                    {
                        "runtime_id": runtime_id,
                        "deleted": True,
                        "idempotent": True,
                        "sanitization": sanitation,
                    },
                )

            if action == "delete":
                return JobExecutionResult(
                    "succeeded",
                    {
                        "runtime_id": runtime_id,
                        "deleted": True,
                        "idempotent": True,
                        "sanitization": {
                            "sanitized": True,
                            "runtime_state_deleted": True,
                            "paired_clients_remaining": 0,
                            "recorded_launcher_pid": None,
                            "recorded_launcher_alive": False,
                            "recorded_launcher_terminated": True,
                            "ownership_schema_version": 2,
                            "runtime_ownership": {
                                "ownership_type": "state_absent",
                                "owned_processes_before": [],
                                "owned_processes_remaining": [],
                                "owned_process_count_before": 0,
                                "owned_process_count_remaining": 0,
                                "termination_verified": True,
                                "ownership_boundary_verified": True,
                            },
                        },
                    },
                )
            raise GamingRuntimeError("Gaming runtime does not exist on this node.")

        sanitation: dict[str, Any] | None = None

        # cleanup_required is a durable fail-closed recovery state.
        # START must never create another workload/ownership boundary
        # until the recorded failed-launch boundary has been proven
        # clean. STOP/DELETE are the explicit recovery operations.
        if (
            action == "start"
            and (
                state.get("status")
                == "cleanup_required"
                or state.get("runtime_stage")
                == "launch_recovery_pending"
            )
        ):
            raise GamingRuntimeError(
                "Gaming runtime requires verified cleanup before "
                "it can be started again."
            )

        # A schema-v2 STOP that has already structurally terminated its
        # ownership boundary is idempotent only when the persisted proof
        # still establishes: boundary verified, termination verified,
        # and zero owned processes. Never reopen/terminate a dead Job
        # Object merely because a duplicate stop job arrives.
        if (
            action == "stop"
            and state.get("status") == "stopped"
            and int(state.get("schema_version") or 1) >= 2
        ):
            stopped_ownership = state.get(
                "runtime_ownership"
            )

            if not isinstance(stopped_ownership, dict):
                raise GamingRuntimeError(
                    "Stopped runtime has no structural ownership proof; "
                    "refusing idempotent stop."
                )

            stopped_remaining = int(
                stopped_ownership.get(
                    "owned_process_count_remaining",
                    stopped_ownership.get(
                        "owned_process_count",
                        0,
                    ),
                )
                or 0
            )

            if (
                bool(
                    stopped_ownership.get(
                        "ownership_boundary_verified"
                    )
                )
                and bool(
                    stopped_ownership.get(
                        "termination_verified"
                    )
                )
                and stopped_remaining == 0
            ):
                return JobExecutionResult(
                    "succeeded",
                    {
                        "runtime_id": runtime_id,
                        "status": "stopped",
                        "idempotent": True,
                        "deployment_stage": "stopped",
                    },
                )

            raise GamingRuntimeError(
                "Stopped runtime ownership is not authoritatively clean; "
                "refusing idempotent stop."
            )

        if (
            action in {"stop", "delete"}
            and (
                state.get("runtime_stage")
                == "launch_recovery_pending"
                or isinstance(state.get("launch_attempt"), dict)
            )
        ):
            pending_cleanup = (
                _cleanup_pending_launch_attempt(
                    state
                )
            )

            if not bool(
                pending_cleanup.get("verified")
            ):
                recovered_ownership = (
                    pending_cleanup.get(
                        "runtime_ownership"
                    )
                )

                if isinstance(
                    recovered_ownership,
                    dict,
                ):
                    # A late workload was identified but could not be
                    # proven terminated. Preserve that exact ownership
                    # boundary for subsequent cleanup.
                    state["status"] = (
                        "cleanup_required"
                    )
                    state["runtime_stage"] = (
                        "cleanup_required"
                    )
                    state["runtime_ownership"] = (
                        dict(recovered_ownership)
                    )
                    state["cleanup"] = (
                        pending_cleanup
                    )
                    _write_state(
                        state_file,
                        state,
                    )

                raise GamingRuntimeError(
                    "Pending Steam launch attempt could not "
                    "be proven sanitized; refusing runtime "
                    "repool."
                )

            proof = dict(
                pending_cleanup.get(
                    "termination_proof"
                )
                or {}
            )

            state["runtime_ownership"] = (
                _terminated_ownership_from_proof(
                    runtime_id=runtime_id,
                    proof=proof,
                    retirement_reason=(
                        "late_launch_sanitized_before_"
                        + action
                    ),
                )
            )

            state["runtime_stage"] = (
                "deleting"
                if action == "delete"
                else "stopping"
            )

            state.pop(
                "launch_attempt",
                None,
            )
            state.pop(
                "launch_failure",
                None,
            )
            state.pop(
                "pre_launch_runtime_ownership",
                None,
            )
            state.pop("workload_launch", None)

            state["runtime_reconciliation"] = {
                "state":
                    "late_launch_cleanup_completed",
                "attempt_id":
                    pending_cleanup.get(
                        "attempt_id"
                    ),
                "action":
                    action,
            }

            _write_state(
                state_file,
                state,
            )

        if action in {"stop", "delete"}:
            if (
                state.get("status") == "running"
                and state.get("runtime_stage") == "stream_ready"
                and isinstance(
                    state.get("workload_observation"),
                    dict,
                )
            ):
                state, _ = _reconcile_customer_workload_state(
                    state
                )
                _write_state(state_file, state)

            paired_clients = [
                item
                for item in state.get("paired_clients", [])
                if isinstance(item, dict)
            ]

            for client in paired_clients:
                client_uuid = str(client.get("sunshine_client_uuid") or "")
                if client_uuid:
                    unpair_client(
                        client_uuid=client_uuid,
                        api_url=sunshine_api_url,
                        username=sunshine_api_username,
                        password=sunshine_api_password,
                        verify_tls=sunshine_verify_tls,
                    )

            state["paired_clients"] = []
            launcher_pid = _recorded_launcher_pid(state)

            ownership = state.get(
                "runtime_ownership"
            )

            if (
                int(state.get("schema_version") or 1) >= 2
                and isinstance(ownership, dict)
            ):
                terminal_proof = (
                    _verified_terminated_ownership(
                        ownership
                    )
                )

                if terminal_proof is not None:
                    ownership_proof = terminal_proof
                else:
                    try:
                        ownership_proof = (
                            terminate_runtime_ownership(
                                ownership
                            )
                        )
                    except RuntimeOwnershipError as exc:
                        raise GamingRuntimeError(
                            "Customer runtime ownership could not "
                            f"be proven clean: {exc}"
                        ) from exc

                launcher_alive = (
                    _process_alive(launcher_pid)
                    if launcher_pid is not None
                    else False
                )

                launcher_stopped = (
                    not launcher_alive
                )

                sanitation = {
                    "paired_clients_remaining": 0,
                    "recorded_launcher_pid":
                        launcher_pid,
                    "recorded_launcher_alive": launcher_alive,
                    "recorded_launcher_terminated":
                        launcher_stopped,
                    "ownership_schema_version":
                        OWNERSHIP_SCHEMA_VERSION,
                    "runtime_ownership":
                        ownership_proof,
                }

                if (
                    not bool(
                        ownership_proof.get(
                            "ownership_boundary_verified"
                        )
                    )
                    or not bool(
                        ownership_proof.get(
                            "termination_verified"
                        )
                    )
                    or int(
                        ownership_proof.get(
                            "owned_process_count_remaining"
                        )
                        or 0
                    )
                    != 0
                    or launcher_alive
                ):
                    raise GamingRuntimeError(
                        "Customer runtime ownership boundary "
                        "could not be sanitized completely; "
                        "refusing runtime repool."
                    )
            else:
                # Runtime-state V1 predates structural process
                # ownership. A persisted launcher PID is not durable
                # identity: Windows/POSIX may reuse that PID after the
                # original process exits or after an agent restart.
                #
                # Therefore a legacy runtime with a recorded PID must
                # fail closed instead of destructively acting on that
                # PID. This prevents an old customer-session record
                # from terminating an unrelated process that later
                # inherited the same numeric PID.
                launcher_alive = (
                    _process_alive(launcher_pid)
                    if launcher_pid is not None
                    else False
                )

                sanitation = {
                    "paired_clients_remaining": 0,
                    "recorded_launcher_pid":
                        launcher_pid,
                    "recorded_launcher_alive":
                        launcher_alive,
                    "recorded_launcher_terminated":
                        False,
                    "ownership_schema_version": 1,
                    "runtime_ownership": {
                        "ownership_type":
                            "legacy_launcher_pid",
                        "ownership_boundary_verified":
                            False,
                        "termination_verified":
                            False,
                        "owned_process_count_remaining":
                            int(launcher_alive),
                        "reason":
                            "legacy_pid_identity_unverifiable",
                    },
                }

                legacy_retirement = bool(
                    action == "delete"
                    and payload.get("legacy_retirement")
                )

                if legacy_retirement:
                    retirement = _legacy_retirement_evidence(
                        payload=payload,
                        state=state,
                        state_file=state_file,
                        runtime_id=runtime_id,
                    )

                    archive_file = state_file.with_name(
                        state_file.name
                        + ".legacy-retired-"
                        + retirement["state_sha256"]
                    )

                    if archive_file.exists():
                        if (
                            hashlib.sha256(
                                archive_file.read_bytes()
                            ).hexdigest().upper()
                            != retirement["state_sha256"]
                        ):
                            raise GamingRuntimeError(
                                "Legacy retirement archive exists "
                                "with an unexpected hash."
                            )
                        state_file.unlink(missing_ok=True)
                    else:
                        state_file.replace(archive_file)

                    state_deleted = not state_file.exists()
                    state_archived = archive_file.exists()

                    retirement["state_archived"] = state_archived
                    retirement["archive_path"] = str(archive_file)

                    sanitation = {
                        "paired_clients_remaining": 0,
                        "recorded_launcher_pid":
                            launcher_pid,
                        "recorded_launcher_alive":
                            bool(
                                retirement[
                                    "recorded_launcher_alive"
                                ]
                            ),
                        "recorded_launcher_terminated": False,
                        "ownership_schema_version": 1,
                        "runtime_ownership": {
                            "ownership_type":
                                "legacy_operator_retirement",
                            "ownership_boundary_verified": False,
                            "termination_verified": False,
                            "owned_process_count_remaining": 0,
                            "reason":
                                "legacy_runtime_retired_by_evidence",
                        },
                        "legacy_retirement": retirement,
                        "runtime_state_deleted": state_deleted,
                        "sanitized": (
                            state_deleted
                            and state_archived
                            and int(
                                retirement[
                                    "game_process_count"
                                ]
                            ) == 0
                            and int(
                                retirement[
                                    "supervisor_process_count"
                                ]
                            ) == 0
                            and not bool(
                                retirement[
                                    "destructive_pid_termination_performed"
                                ]
                            )
                            and (
                                not bool(
                                    retirement[
                                        "recorded_launcher_alive"
                                    ]
                                )
                                or bool(
                                    retirement[
                                        "recorded_pid_identity_reused"
                                    ]
                                )
                            )
                        ),
                    }

                    if not sanitation["sanitized"]:
                        raise GamingRuntimeError(
                            "Legacy retirement evidence did not "
                            "satisfy the sanitation contract."
                        )

                    return JobExecutionResult(
                        "succeeded",
                        {
                            "runtime_id": runtime_id,
                            "deleted": True,
                            "sanitization": sanitation,
                        },
                    )

                if launcher_pid is not None:
                    raise GamingRuntimeError(
                        "Legacy runtime process ownership cannot "
                        "be proven from launcher PID alone; "
                        "refusing destructive PID termination "
                        "and runtime repool."
                    )

        if action == "delete":
            try:
                state_file.unlink()
            except FileNotFoundError:
                pass

            state_deleted = not state_file.exists()
            assert sanitation is not None
            sanitation.update(
                {
                    "runtime_state_deleted": state_deleted,
                    "sanitized": (
                        state_deleted
                        and int(
                            sanitation.get(
                                "paired_clients_remaining",
                                0,
                            )
                        )
                        == 0
                        and not bool(
                            sanitation.get(
                                "recorded_launcher_alive"
                            )
                        )
                        and (
                            int(
                                sanitation.get(
                                    "ownership_schema_version"
                                )
                                or 0
                            )
                            >= 2
                            and (
                                bool(
                                    (
                                        sanitation.get(
                                            "runtime_ownership"
                                        )
                                        or {}
                                    ).get(
                                        "ownership_boundary_verified"
                                    )
                                )
                                and bool(
                                    (
                                        sanitation.get(
                                            "runtime_ownership"
                                        )
                                        or {}
                                    ).get(
                                        "termination_verified"
                                    )
                                )
                                and int(
                                    (
                                        sanitation.get(
                                            "runtime_ownership"
                                        )
                                        or {}
                                    ).get(
                                        "owned_process_count_remaining"
                                    )
                                    or 0
                                )
                                == 0
                            )
                        )
                    ),
                }
            )
            if not bool(sanitation["sanitized"]):
                raise GamingRuntimeError("Gaming runtime sanitization proof failed.")

            return JobExecutionResult(
                "succeeded",
                {
                    "runtime_id": runtime_id,
                    "deleted": True,
                    "sanitization": sanitation,
                },
            )

        gpu_uuid = str(state.get("gpu_uuid") or "")
        minimum_vram_mb = int(state.get("minimum_vram_mb") or 8192)
        _validate_windows_native(
            gpu_uuid=gpu_uuid,
            minimum_vram_mb=minimum_vram_mb,
            execution_backend=execution_backend,
            streaming_backend=streaming_backend,
        )

        desired = "running" if action == "start" else "stopped"

        # STOP is a structural runtime teardown in ownership schema V2.
        # Once the Job/process boundary has been proven empty, persist that
        # proof so an idempotent second stop never attempts to act on a dead
        # ownership boundary.
        if desired == "stopped":
            if state.get("status") == "stopped":
                return JobExecutionResult(
                    "succeeded",
                    {
                        "runtime_id": runtime_id,
                        "status": "stopped",
                        "idempotent": True,
                        "deployment_stage": "stopped",
                        **(
                            {"sanitization": sanitation}
                            if sanitation is not None
                            else {}
                        ),
                    },
                )

            state["status"] = "stopped"
            state["runtime_stage"] = "stopped"

            if sanitation is not None:
                proof = dict(
                    sanitation.get("runtime_ownership")
                    or {}
                )
                state["runtime_ownership"] = {
                    "schema_version":
                        OWNERSHIP_SCHEMA_VERSION,
                    "ownership_type":
                        "terminated",
                    "runtime_id":
                        runtime_id,
                    "ownership_boundary_verified":
                        bool(
                            proof.get(
                                "ownership_boundary_verified"
                            )
                        ),
                    "termination_verified":
                        bool(
                            proof.get(
                                "termination_verified"
                            )
                        ),
                    "owned_process_count":
                        int(
                            proof.get(
                                "owned_process_count_remaining"
                            )
                            or 0
                        ),
                    "owned_process_count_remaining":
                        int(
                            proof.get(
                                "owned_process_count_remaining"
                            )
                            or 0
                        ),
                    "clean": (
                        bool(
                            proof.get(
                                "ownership_boundary_verified"
                            )
                        )
                        and bool(
                            proof.get(
                                "termination_verified"
                            )
                        )
                        and int(
                            proof.get(
                                "owned_process_count_remaining"
                            )
                            or 0
                        )
                        == 0
                    ),
                }

            # A stopped runtime no longer has a live launcher identity.
            # Preserve the restart recipe separately, but never leave a PID
            # or stale launch-attempt authority that could later be mistaken
            # for current ownership.
            state.pop("launch_info", None)
            state.pop("launch_attempt", None)
            state.pop("launch_failure", None)
            state.pop("workload_observation", None)
            state.pop("workload_launch", None)
            state.pop("last_play", None)
            state.pop(
                "pre_launch_runtime_ownership",
                None,
            )

            _write_state(state_file, state)

            return JobExecutionResult(
                "succeeded",
                {
                    "runtime_id": runtime_id,
                    "status": "stopped",
                    "deployment_stage": "stopped",
                    **(
                        {"sanitization": sanitation}
                        if sanitation is not None
                        else {}
                    ),
                },
            )

        # START after a structural STOP must create a new runtime ownership
        # boundary. Merely changing persisted state to "running" would claim
        # that a customer runtime exists after its process tree was destroyed.
        #
        # Preserve the durable STOP proof while START is in-flight. If no new
        # runtime ownership boundary is successfully returned, failed START
        # must restore this proof rather than weakening it to "none".
        stopped_ownership_before_start = (
            dict(state.get("runtime_ownership") or {})
            if isinstance(state.get("runtime_ownership"), dict)
            else None
        )

        trace.emit("managed_session_validation_begin")
        interactive_session = (
            _interactive_session_context()
        )
        trace.emit(
            "managed_session_validation_end",
            validated=bool(interactive_session.get("validated")),
        )
        state["interactive_session"] = (
            interactive_session
        )

        if state.get("status") == "running":
            ownership = state.get("runtime_ownership")
            if not isinstance(ownership, dict):
                raise GamingRuntimeError(
                    "Running runtime has no structural ownership metadata."
                )

            launch_info = state.get("launch_info")
            if launch_info is not None and not isinstance(
                launch_info,
                dict,
            ):
                raise GamingRuntimeError(
                    "Running runtime launch metadata is invalid."
                )

            display_activation = None
            display_policy = state.get("display_policy")
            if isinstance(display_policy, dict):
                candidate = display_policy.get("activation")
                if isinstance(candidate, dict):
                    display_activation = candidate

            try:
                readiness = _verify_stream_readiness(
                    runtime_id=runtime_id,
                    runtime_ownership=ownership,
                    launch_info=launch_info,
                    display_activation=display_activation,
                    sunshine_api_url=sunshine_api_url,
                    sunshine_api_username=sunshine_api_username,
                    sunshine_api_password=sunshine_api_password,
                    sunshine_verify_tls=sunshine_verify_tls,
                )
            except Exception:
                state.pop(
                    "stream_readiness",
                    None,
                )
                state[
                    "runtime_stage"
                ] = "readiness_pending"
                state["interactive_session"] = (
                    interactive_session
                )
                _write_state(
                    state_file,
                    state,
                )
                raise

            state["interactive_session"] = (
                interactive_session
            )
            state["stream_readiness"] = readiness
            state["runtime_stage"] = "stream_ready"
            _write_state(state_file, state)

            return JobExecutionResult(
                "succeeded",
                {
                    "runtime_id": runtime_id,
                    "status": "running",
                    "idempotent": True,
                    "connection_info":
                        _connection_info(runtime_id),
                    "deployment_stage":
                        "stream_ready",
                    "interactive_session":
                        interactive_session,
                    "stream_readiness":
                        readiness,
                },
            )

        trace.emit("display_prerequisites_begin")
        display_activation = None
        display_policy = state.get("display_policy")
        if isinstance(display_policy, dict):
            candidate = display_policy.get("activation")
            if isinstance(candidate, dict):
                display_activation = candidate

        presentation_contract = (
            _establish_presentation_contract(
                interactive_session
            )
        )
        state["presentation_contract"] = (
            presentation_contract
        )
        trace.emit("display_prerequisites_end")

        game_slug = str(
            state.get("game_slug") or ""
        ).strip()
        launcher_type = str(
            state.get("launcher_type")
            or state.get("launcher")
            or ""
        ).strip()
        launcher_game_id = str(
            state.get("launcher_game_id")
            or state.get("launcher_app_id")
            or ""
        ).strip()

        restart_payload = {
            "session_id": session_id,
            "gpu_uuid": gpu_uuid,
            "minimum_vram_mb": minimum_vram_mb,
        }

        if game_slug:
            restart_payload["game_slug"] = game_slug
        if launcher_type:
            restart_payload["launcher_type"] = (
                launcher_type
            )
        if launcher_game_id:
            restart_payload["launcher_game_id"] = (
                launcher_game_id
            )

        trace.emit("steam_inventory_readiness_begin")
        prepared_launch = prepare_game_launch(
            restart_payload
        )
        trace.emit(
            "steam_inventory_readiness_end",
            has_prepared_launch=prepared_launch is not None,
        )
        trace.emit("runtime_preparation_end")

        # Q38IU-Y44C-R2:
        # Restart restores the commercial resource/stream session and
        # revalidates the assigned installed game. It must never
        # automatically relaunch the customer's previous workload.
        launch_info: dict[str, Any] | None = None

        if prepared_launch is not None:
            prepared_launch = replace(
                prepared_launch,
                runtime_id=runtime_id,
                expected_session_id=(
                    interactive_session.get("session_id")
                    if interactive_session.get("validated")
                    else None
                ),
                presentation_contract=presentation_contract,
            )

        workload_observation = (
            _prepared_workload_observation(
                runtime_id=runtime_id,
                prepared_launch=prepared_launch,
                interactive_session=interactive_session,
            )
        )

        runtime_ownership = (
            dict(
                launch_info.get(
                    "runtime_ownership"
                ) or {}
            )
            if launch_info is not None
            else no_process_ownership()
        )

        trace.emit("stream_readiness_begin")
        try:
            readiness = _verify_stream_readiness(
                runtime_id=runtime_id,
                runtime_ownership=runtime_ownership,
                launch_info=launch_info,
                display_activation=display_activation,
                sunshine_api_url=sunshine_api_url,
                sunshine_api_username=sunshine_api_username,
                sunshine_api_password=sunshine_api_password,
                sunshine_verify_tls=sunshine_verify_tls,
            )
        except Exception as readiness_exc:
            trace.emit("stream_readiness_end", verified=False,
                       error_type=type(readiness_exc).__name__)
            cleanup = {
                "verified": True,
                "runtime_ownership":
                    no_process_ownership(),
                "termination_proof":
                    terminate_runtime_ownership(
                        no_process_ownership()
                    ),
                "error": None,
            }

            if launch_info is not None:
                cleanup = _cleanup_failed_launch(
                    runtime_ownership
                )

            state.pop(
                "stream_readiness",
                None,
            )

            if cleanup["verified"]:
                state["status"] = "stopped"
                state["runtime_stage"] = "stopped"

                if launch_info is None:
                    state["runtime_ownership"] = (
                        dict(stopped_ownership_before_start)
                        if stopped_ownership_before_start is not None
                        else no_process_ownership()
                    )
                else:
                    termination_proof = dict(
                        cleanup.get("termination_proof")
                        or cleanup.get("runtime_ownership")
                        or {}
                    )
                    remaining = int(
                        termination_proof.get(
                            "owned_process_count_remaining",
                            termination_proof.get(
                                "owned_process_count",
                                0,
                            ),
                        )
                        or 0
                    )
                    boundary_verified = bool(
                        termination_proof.get(
                            "ownership_boundary_verified"
                        )
                    )
                    termination_verified = bool(
                        termination_proof.get(
                            "termination_verified"
                        )
                    )

                    state["runtime_ownership"] = {
                        "schema_version":
                            OWNERSHIP_SCHEMA_VERSION,
                        "ownership_type":
                            "terminated",
                        "runtime_id":
                            runtime_id,
                        "ownership_boundary_verified":
                            boundary_verified,
                        "termination_verified":
                            termination_verified,
                        "owned_process_count":
                            remaining,
                        "owned_process_count_remaining":
                            remaining,
                        "clean": (
                            boundary_verified
                            and termination_verified
                            and remaining == 0
                        ),
                    }

                state.pop(
                    "launch_info",
                    None,
                )
                state.pop(
                    "readiness_failure",
                    None,
                )
                state.pop(
                    "cleanup",
                    None,
                )
                state.pop(
                    "launch_attempt",
                    None,
                )
                state.pop(
                    "launch_failure",
                    None,
                )
                state.pop(
                    "pre_launch_runtime_ownership",
                    None,
                )
            else:
                state["status"] = (
                    "cleanup_required"
                )
                state["runtime_stage"] = (
                    "cleanup_required"
                )
                state["runtime_ownership"] = (
                    runtime_ownership
                )

                if launch_info is not None:
                    state["launch_info"] = (
                        launch_info
                    )

                state[
                    "readiness_failure"
                ] = {
                    "type":
                        type(
                            readiness_exc
                        ).__name__,
                    "message":
                        str(readiness_exc),
                }
                state["cleanup"] = cleanup

            _write_state(
                state_file,
                state,
            )
            raise

        trace.emit("stream_readiness_end", verified=True)
        state["status"] = "running"
        state["runtime_stage"] = "stream_ready"
        state["runtime_ownership"] = runtime_ownership
        if workload_observation is not None:
            state["workload_observation"] = workload_observation
        else:
            state.pop("workload_observation", None)
        state["stream_readiness"] = readiness
        state.pop("launch_attempt", None)
        state.pop("launch_failure", None)
        state.pop(
            "pre_launch_runtime_ownership",
            None,
        )

        if prepared_launch is not None:
            state["game_slug"] = (
                prepared_launch.game_slug
            )
            state["launcher_type"] = (
                prepared_launch.launcher_type
            )
            state["launcher_game_id"] = (
                prepared_launch.launcher_game_id
            )
            state["launcher"] = (
                prepared_launch.launcher_type
            )
            state["launcher_app_id"] = (
                prepared_launch.launcher_game_id
            )
            state["game"] = prepared_launch.game

        if launch_info is not None:
            state["launch_info"] = launch_info
        else:
            state.pop("launch_info", None)

        _write_state(state_file, state)

        result: dict[str, Any] = {
            "runtime_id": runtime_id,
            "status": "running",
            "deployment_stage": "stream_ready",
            "connection_info":
                _connection_info(runtime_id),
            "interactive_session":
                interactive_session,
            "presentation_contract":
                presentation_contract,
            "stream_readiness":
                readiness,
        }

        if prepared_launch is not None:
            result["game"] = prepared_launch.game
            result["game_slug"] = prepared_launch.game_slug
            result["launcher_type"] = (
                prepared_launch.launcher_type
            )
            result["launcher_game_id"] = (
                prepared_launch.launcher_game_id
            )

        if launch_info is not None:
            result["launch_info"] = launch_info

        return JobExecutionResult(
            "succeeded",
            result,
        )
    except (
        GamingRuntimeError,
        GameLaunchError,
        SunshineBrokerError,
        ValueError,
    ) as exc:
        return JobExecutionResult("blocked", {}, str(exc))



def pair_connection(
    payload: dict[str, Any],
    *,
    state_root: Path,
    sunshine_api_url: str,
    sunshine_api_username: str,
    sunshine_api_password: str,
    sunshine_verify_tls: bool,
) -> JobExecutionResult:
    session_id = str(payload.get("session_id") or "")
    pin = str(payload.get("pin") or "")
    client_name = str(payload.get("client_name") or "")

    try:
        _, runtime_id, state_file = _state_paths(
            state_root,
            session_id,
        )
        state = _read_state(state_file)

        if state is None:
            raise GamingRuntimeError(
                "Gaming runtime does not exist on this node."
            )

        if state.get("status") != "running":
            raise GamingRuntimeError(
                "Gaming connection pairing requires a running runtime."
            )

        if state.get("runtime_stage") != "stream_ready":
            raise GamingRuntimeError(
                "Gaming connection pairing requires a stream-ready runtime."
            )

        readiness = state.get("stream_readiness")
        if (
            not isinstance(readiness, dict)
            or not bool(readiness.get("verified"))
        ):
            raise GamingRuntimeError(
                "Gaming connection pairing requires verified "
                "stream readiness."
            )

        paired = pair_client(
            pin=pin,
            client_name=client_name,
            api_url=sunshine_api_url,
            username=sunshine_api_username,
            password=sunshine_api_password,
            verify_tls=sunshine_verify_tls,
        )

        clients = [
            item
            for item in state.get("paired_clients", [])
            if isinstance(item, dict)
        ]

        client_uuid = str(
            paired["sunshine_client_uuid"]
        )

        if not any(
            str(item.get("sunshine_client_uuid"))
            == client_uuid
            for item in clients
        ):
            clients.append(
                {
                    "sunshine_client_uuid": client_uuid,
                    "client_name": client_name,
                }
            )

        state["paired_clients"] = clients
        _write_state(state_file, state)

        return JobExecutionResult(
            "succeeded",
            {
                "runtime_id": runtime_id,
                **paired,
            },
        )

    except (
        GamingRuntimeError,
        SunshineBrokerError,
    ) as exc:
        return JobExecutionResult(
            "blocked",
            {},
            str(exc),
        )


def revoke_connection(
    payload: dict[str, Any],
    *,
    state_root: Path,
    sunshine_api_url: str,
    sunshine_api_username: str,
    sunshine_api_password: str,
    sunshine_verify_tls: bool,
) -> JobExecutionResult:
    session_id = str(payload.get("session_id") or "")
    client_uuid = str(
        payload.get("sunshine_client_uuid") or ""
    )

    try:
        _, runtime_id, state_file = _state_paths(
            state_root,
            session_id,
        )
        state = _read_state(state_file)

        if state is None:
            raise GamingRuntimeError(
                "Gaming runtime does not exist on this node."
            )

        result = unpair_client(
            client_uuid=client_uuid,
            api_url=sunshine_api_url,
            username=sunshine_api_username,
            password=sunshine_api_password,
            verify_tls=sunshine_verify_tls,
        )

        clients = [
            item
            for item in state.get("paired_clients", [])
            if (
                isinstance(item, dict)
                and str(
                    item.get("sunshine_client_uuid")
                ) != client_uuid
            )
        ]

        state["paired_clients"] = clients
        _write_state(state_file, state)

        return JobExecutionResult(
            "succeeded",
            {
                "runtime_id": runtime_id,
                **result,
            },
        )

    except (
        GamingRuntimeError,
        SunshineBrokerError,
    ) as exc:
        return JobExecutionResult(
            "blocked",
            {},
            str(exc),
        )




def _terminated_ownership_from_proof(
    *,
    runtime_id: str,
    proof: dict[str, Any],
    retirement_reason: str,
) -> dict[str, Any]:
    """
    Normalize any successfully sanitized structural ownership proof into
    the canonical durable schema-v2 terminal descriptor.
    """
    remaining = int(
        proof.get(
            "owned_process_count_remaining",
            proof.get(
                "owned_process_count",
                0,
            ),
        )
        or 0
    )

    boundary_verified = bool(
        proof.get(
            "ownership_boundary_verified"
        )
    )
    termination_verified = bool(
        proof.get(
            "termination_verified"
        )
    )

    clean = (
        boundary_verified
        and termination_verified
        and remaining == 0
    )

    return {
        "schema_version":
            OWNERSHIP_SCHEMA_VERSION,
        "ownership_type":
            "terminated",
        "runtime_id":
            str(runtime_id),
        "ownership_boundary_verified":
            boundary_verified,
        "termination_verified":
            termination_verified,
        "owned_process_count":
            remaining,
        "owned_process_count_remaining":
            remaining,
        "clean":
            clean,
        "retirement_reason":
            str(retirement_reason),
    }



def _inspect_pending_launch_attempt(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Inspect a durable asynchronous launch attempt.

    This helper never performs process-name sweeping. It delegates process
    correlation to the exact persisted baseline/session/install-root
    authority in windows_verified_process.
    """
    from khan_agent.windows_verified_process import (
        classify_launch_attempt_recovery,
        ownership_from_launch_attempt,
    )

    authority = state.get("launch_attempt")
    if not isinstance(authority, dict) and str(
        state.get("runtime_stage") or ""
    ) != "launch_recovery_pending":
        return {"state": "not_pending"}

    if not isinstance(authority, dict):
        raise GamingRuntimeError(
            "Launch recovery is pending without durable "
            "launch-attempt authority."
        )

    result = classify_launch_attempt_recovery(
        authority
    )

    if result["state"] == "candidate_discovered":
        ownership = ownership_from_launch_attempt(
            authority,
            result["processes"],
        )
        return {
            **result,
            "runtime_ownership": ownership,
        }

    return result




def _cleanup_pending_launch_attempt(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Sanitize a pending asynchronous Steam attempt only when exact
    persisted authority discovers an attributable workload.

    No-candidate states never become clean merely because time elapsed.
    """
    recovery = _inspect_pending_launch_attempt(
        state
    )

    recovery_state = str(
        recovery.get("state") or ""
    )

    if recovery_state in {
        "pending",
        "expired_no_candidate",
    }:
        return {
            "verified": False,
            "recovery_state":
                recovery_state,
            "attempt_id":
                recovery.get("attempt_id"),
            "runtime_ownership": None,
            "termination_proof": None,
            "error": (
                "launch_attempt_still_pending"
                if recovery_state == "pending"
                else
                "launch_attempt_expired_without_cleanliness_proof"
            ),
        }

    if recovery_state != "candidate_discovered":
        raise GamingRuntimeError(
            "Pending launch cleanup received an "
            "unexpected recovery state."
        )

    ownership = dict(
        recovery["runtime_ownership"]
    )

    try:
        proof = terminate_runtime_ownership(
            ownership
        )
    except Exception as exc:
        return {
            "verified": False,
            "recovery_state":
                "candidate_discovered",
            "attempt_id":
                recovery.get("attempt_id"),
            "runtime_ownership":
                ownership,
            "termination_proof":
                None,
            "error":
                f"{type(exc).__name__}: {exc}",
        }

    remaining = int(
        proof.get(
            "owned_process_count_remaining",
            proof.get(
                "owned_process_count",
                0,
            ),
        )
        or 0
    )

    verified = (
        bool(
            proof.get(
                "ownership_boundary_verified"
            )
        )
        and bool(
            proof.get(
                "termination_verified"
            )
        )
        and remaining == 0
    )

    return {
        "verified":
            verified,
        "recovery_state":
            "candidate_discovered",
        "attempt_id":
            recovery.get("attempt_id"),
        "runtime_ownership":
            ownership,
        "termination_proof":
            dict(proof),
        "error": (
            None
            if verified
            else
            "late_launch_termination_not_verified"
        ),
    }



def reconcile_runtime_ownership(
    state_root: Path,
) -> list[dict[str, Any]]:
    """Reconcile durable D1 runtime ownership after agent restart.

    Unknown/unverifiable ownership fails closed. This function never
    performs process-name sweeping and never kills a process outside a
    structurally recorded runtime boundary.
    """

    paths = GamingRuntimePaths(
        Path(state_root)
    )

    if not paths.sessions_dir.exists():
        return []

    outcomes: list[dict[str, Any]] = []

    for state_file in sorted(
        paths.sessions_dir.glob(
            "kc-gaming-*.json"
        )
    ):
        try:
            state = _read_state(state_file)

            if state is None:
                continue

            if int(
                state.get("schema_version") or 1
            ) < 2:
                outcomes.append(
                    {
                        "runtime_id":
                            state.get("runtime_id"),
                        "state": "legacy_v1",
                        "action": "preserved",
                    }
                )
                continue

            if (
                str(state.get("runtime_stage") or "")
                == "launch_recovery_pending"
            ):
                recovery = (
                    _inspect_pending_launch_attempt(
                        state
                    )
                )

                if (
                    recovery.get("state")
                    == "candidate_discovered"
                ):
                    pending_cleanup = (
                        _cleanup_pending_launch_attempt(
                            state
                        )
                    )

                    recovered_ownership = (
                        pending_cleanup.get(
                            "runtime_ownership"
                        )
                    )

                    if not bool(
                        pending_cleanup.get(
                            "verified"
                        )
                    ):
                        state["status"] = (
                            "cleanup_required"
                        )
                        state["runtime_stage"] = (
                            "cleanup_required"
                        )

                        if isinstance(
                            recovered_ownership,
                            dict,
                        ):
                            state[
                                "runtime_ownership"
                            ] = dict(
                                recovered_ownership
                            )

                        state["cleanup"] = (
                            pending_cleanup
                        )
                        state[
                            "runtime_reconciliation"
                        ] = {
                            "state":
                                "cleanup_required",
                            "reason":
                                "late_launch_cleanup_not_verified",
                            "attempt_id":
                                pending_cleanup.get(
                                    "attempt_id"
                                ),
                        }

                        _write_state(
                            state_file,
                            state,
                        )

                        outcomes.append(
                            {
                                "runtime_id":
                                    state.get(
                                        "runtime_id"
                                    ),
                                "state":
                                    "cleanup_required",
                            }
                        )
                        continue

                    proof = dict(
                        pending_cleanup.get(
                            "termination_proof"
                        )
                        or {}
                    )

                    state["status"] = "stopped"
                    state["runtime_stage"] = (
                        "stopped"
                    )
                    state["runtime_ownership"] = (
                        _terminated_ownership_from_proof(
                            runtime_id=str(
                                state.get(
                                    "runtime_id"
                                )
                                or ""
                            ),
                            proof=proof,
                            retirement_reason=(
                                "late_launch_reconciled_and_sanitized"
                            ),
                        )
                    )

                    state.pop(
                        "launch_info",
                        None,
                    )
                    state.pop(
                        "stream_readiness",
                        None,
                    )
                    state.pop(
                        "launch_attempt",
                        None,
                    )
                    state.pop(
                        "launch_failure",
                        None,
                    )
                    state.pop(
                        "pre_launch_runtime_ownership",
                        None,
                    )
                    state.pop(
                        "cleanup",
                        None,
                    )

                    state[
                        "runtime_reconciliation"
                    ] = {
                        "state":
                            "late_launch_cleanup_completed",
                        "attempt_id":
                            pending_cleanup.get(
                                "attempt_id"
                            ),
                    }

                    _write_state(
                        state_file,
                        state,
                    )

                    outcomes.append(
                        {
                            "runtime_id":
                                state.get(
                                    "runtime_id"
                                ),
                            "state":
                                "late_launch_cleanup_completed",
                        }
                    )
                    continue

                if recovery.get("state") == "pending":
                    state[
                        "runtime_reconciliation"
                    ] = {
                        "state":
                            "launch_recovery_pending",
                        "attempt_id":
                            recovery.get("attempt_id"),
                    }
                    _write_state(
                        state_file,
                        state,
                    )
                    outcomes.append(
                        {
                            "runtime_id":
                                state.get("runtime_id"),
                            "state":
                                "launch_recovery_pending",
                        }
                    )
                    continue

                if (
                    recovery.get("state")
                    == "expired_no_candidate"
                ):
                    # Expiry ends automatic attribution but is not itself
                    # proof that Steam can never materialize a later game.
                    # Keep the state fail-closed and require an explicit
                    # sanitation/recovery operation before another START.
                    state["status"] = (
                        "cleanup_required"
                    )
                    state["runtime_stage"] = (
                        "cleanup_required"
                    )
                    state[
                        "runtime_reconciliation"
                    ] = {
                        "state":
                            "launch_attempt_expired",
                        "attempt_id":
                            recovery.get("attempt_id"),
                        "reason":
                            "expiry_is_not_cleanliness_proof",
                    }
                    state["cleanup"] = {
                        "verified": False,
                        "runtime_ownership":
                            dict(
                                state.get(
                                    "runtime_ownership"
                                )
                                or {}
                            ),
                        "termination_proof": None,
                        "error":
                            "launch_attempt_expired_without_candidate",
                    }
                    _write_state(
                        state_file,
                        state,
                    )
                    outcomes.append(
                        {
                            "runtime_id":
                                state.get("runtime_id"),
                            "state":
                                "launch_attempt_expired",
                        }
                    )
                    continue

                raise GamingRuntimeError(
                    "Launch-attempt recovery returned an "
                    "unknown state."
                )

            ownership = state.get(
                "runtime_ownership"
            )

            if not isinstance(
                ownership,
                dict,
            ):
                state[
                    "runtime_reconciliation"
                ] = {
                    "state": "fail_closed",
                    "reason":
                        "ownership_descriptor_missing",
                }
                _write_state(
                    state_file,
                    state,
                )
                outcomes.append(
                    {
                        "runtime_id":
                            state.get("runtime_id"),
                        "state": "fail_closed",
                    }
                )
                continue

            inspection = (
                inspect_runtime_ownership(
                    ownership
                )
            )

            if not bool(
                inspection.get(
                    "ownership_boundary_verified"
                )
            ):
                state[
                    "runtime_reconciliation"
                ] = {
                    "state": "fail_closed",
                    "inspection": inspection,
                }
                _write_state(
                    state_file,
                    state,
                )
                outcomes.append(
                    {
                        "runtime_id":
                            state.get("runtime_id"),
                        "state": "fail_closed",
                    }
                )
                continue

            status = str(
                state.get("status") or ""
            )

            if status == "cleanup_required":
                try:
                    proof = terminate_runtime_ownership(
                        ownership
                    )
                except Exception as exc:
                    state[
                        "runtime_reconciliation"
                    ] = {
                        "state": "cleanup_required",
                        "reason":
                            "cleanup_termination_failed",
                        "inspection": inspection,
                        "error":
                            f"{type(exc).__name__}: {exc}",
                    }
                    _write_state(
                        state_file,
                        state,
                    )
                    outcomes.append(
                        {
                            "runtime_id":
                                state.get("runtime_id"),
                            "state":
                                "cleanup_required",
                        }
                    )
                    continue

                remaining = int(
                    proof.get(
                        "owned_process_count_remaining",
                        proof.get(
                            "owned_process_count",
                            0,
                        ),
                    )
                    or 0
                )

                cleanup_verified = (
                    bool(
                        proof.get(
                            "ownership_boundary_verified"
                        )
                    )
                    and bool(
                        proof.get(
                            "termination_verified"
                        )
                    )
                    and remaining == 0
                )

                if not cleanup_verified:
                    state[
                        "runtime_reconciliation"
                    ] = {
                        "state": "cleanup_required",
                        "reason":
                            "cleanup_not_verified",
                        "inspection": inspection,
                        "ownership": proof,
                    }
                    state["cleanup"] = {
                        "verified": False,
                        "runtime_ownership":
                            dict(ownership),
                        "termination_proof": proof,
                        "error":
                            "runtime_termination_not_verified",
                    }
                    _write_state(
                        state_file,
                        state,
                    )
                    outcomes.append(
                        {
                            "runtime_id":
                                state.get("runtime_id"),
                            "state":
                                "cleanup_required",
                        }
                    )
                    continue

                state["status"] = "stopped"
                state["runtime_stage"] = "stopped"
                state["runtime_ownership"] = proof
                state["cleanup"] = {
                    "verified": True,
                    "runtime_ownership":
                        dict(ownership),
                    "termination_proof": proof,
                    "error": None,
                }
                state.pop(
                    "launch_info",
                    None,
                )
                state.pop(
                    "stream_readiness",
                    None,
                )
                state.pop(
                    "launch_attempt",
                    None,
                )
                state.pop(
                    "launch_failure",
                    None,
                )
                state.pop(
                    "pre_launch_runtime_ownership",
                    None,
                )
                state[
                    "runtime_reconciliation"
                ] = {
                    "state":
                        "cleanup_completed",
                    "ownership": proof,
                }

                _write_state(
                    state_file,
                    state,
                )

                outcomes.append(
                    {
                        "runtime_id":
                            state.get("runtime_id"),
                        "state":
                            "cleanup_completed",
                    }
                )
                continue

            if (
                status
                in {
                    "stopped",
                    "stopping",
                    "deleting",
                }
                and not bool(
                    inspection.get("clean")
                )
            ):
                proof = (
                    terminate_runtime_ownership(
                        ownership
                    )
                )

                state[
                    "runtime_reconciliation"
                ] = {
                    "state":
                        "cleanup_completed",
                    "ownership": proof,
                }

                _write_state(
                    state_file,
                    state,
                )

                outcomes.append(
                    {
                        "runtime_id":
                            state.get("runtime_id"),
                        "state":
                            "cleanup_completed",
                    }
                )
                continue

            owned_count = int(
                inspection.get(
                    "owned_process_count"
                )
                or 0
            )

            ownership_type = str(
                ownership.get("ownership_type")
                or "none"
            )

            if (
                status in {"running", "starting"}
                and owned_count == 0
                and ownership_type != "none"
            ):
                state["status"] = "stopped"
                state["runtime_stage"] = "stopped"
                state["runtime_ownership"] = {
                    "schema_version":
                        OWNERSHIP_SCHEMA_VERSION,
                    "ownership_type":
                        "terminated",
                    "runtime_id":
                        state.get("runtime_id"),
                    "ownership_boundary_verified": True,
                    "termination_verified": True,
                    "owned_process_count": 0,
                    "owned_process_count_remaining": 0,
                    "clean": True,
                    "retirement_reason":
                        "verified_workload_identity_absent",
                }
                state.pop(
                    "launch_info",
                    None,
                )
                state.pop(
                    "stream_readiness",
                    None,
                )
                state[
                    "runtime_reconciliation"
                ] = {
                    "state": "workload_retired",
                    "inspection": inspection,
                    "reason":
                        "verified_runtime_has_no_live_owned_process",
                }

                _write_state(
                    state_file,
                    state,
                )

                outcomes.append(
                    {
                        "runtime_id":
                            state.get("runtime_id"),
                        "state":
                            "workload_retired",
                    }
                )
                continue

            if (
                status == "starting"
                and owned_count > 0
            ):
                state["status"] = "starting"
                state[
                    "runtime_stage"
                ] = "readiness_pending"
                state.pop(
                    "stream_readiness",
                    None,
                )
                state[
                    "runtime_reconciliation"
                ] = {
                    "state":
                        "readiness_pending",
                    "inspection": inspection,
                    "reason":
                        "ownership_survived_but_stream_readiness_requires_authoritative_revalidation",
                }
                _write_state(
                    state_file,
                    state,
                )
                outcomes.append(
                    {
                        "runtime_id":
                            state.get("runtime_id"),
                        "state":
                            "readiness_pending",
                    }
                )
                continue

            state[
                "runtime_reconciliation"
            ] = {
                "state": "verified",
                "inspection": inspection,
            }

            _write_state(
                state_file,
                state,
            )

            outcomes.append(
                {
                    "runtime_id":
                        state.get("runtime_id"),
                    "state": "verified",
                }
            )

        except Exception as exc:
            outcomes.append(
                {
                    "runtime_id":
                        state_file.stem,
                    "state": "fail_closed",
                    "error":
                        f"{type(exc).__name__}: {exc}",
                }
            )

    return outcomes
