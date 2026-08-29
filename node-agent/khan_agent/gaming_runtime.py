from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from khan_agent.file_security import secure_private_file
from khan_agent.gaming_backends import locate_sunshine, probe_nvidia_gpu
from khan_agent.gaming_launchers import (
    GameLaunchError,
    launch_prepared_game,
    prepare_game_launch,
)
from khan_agent.sunshine_broker import (
    SunshineBrokerError,
    pair_client,
    unpair_client,
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
from khan_agent.windows_interactive import (
    InteractiveSessionError,
    active_console_session_id,
)


class GamingRuntimeError(RuntimeError):
    pass


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
    temp.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    secure_private_file(temp)
    os.replace(temp, path)
    secure_private_file(path)


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
        session_id = int(
            active_console_session_id()
        )
    except InteractiveSessionError as exc:
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



def create_session(
    payload: dict[str, Any],
    *,
    state_root: Path,
    execution_backend: str,
    streaming_backend: str,
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
            _write_state(state_file, existing)

            result: dict[str, Any] = {
                "runtime_id": runtime_id,
                "status": str(existing.get("status") or "unknown"),
                "deployment_stage": (
                    "stream_ready"
                    if existing.get("status") == "running"
                    else str(
                        existing.get("runtime_stage")
                        or existing.get("status")
                        or "unknown"
                    )
                ),
                "interactive_session": interactive_session,
                "idempotent": True,
            }

            if existing.get("status") == "running":
                result["connection_info"] = _connection_info(runtime_id)

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

        # KG-009: authoritative last-moment session broker gate.
        # Scheduling heartbeat evidence can become stale after placement;
        # therefore the Windows node verifies the actual console session
        # again before touching VDD state or launching the game.
        interactive_session = (
            _interactive_session_context()
        )

        display_policy_result: dict[str, Any] | None = None

        if display_policy_request is not None:
            display_policy_result = (
                _apply_session_display_policy(
                    display_policy_request,
                    template_path=vdd_template_path,
                    target_root=vdd_target_root,
                )
            )

        # Display policy is validated and atomically persisted
        # before game preparation or launch. Invalid VDD policy
        # therefore fails closed before customer workload start.
        prepared_launch = prepare_game_launch(payload)

        launch_info: dict[str, Any] | None = None

        if prepared_launch is not None:
            launch_info = launch_prepared_game(
                prepared_launch
            )

        state = {
            "schema_version": 1,
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
        }

        if display_policy_result is not None:
            state["display_policy_request"] = (
                display_policy_request
            )
            state["display_policy"] = (
                display_policy_result
            )

        if (
            prepared_launch is not None
            and launch_info is not None
        ):
            state.update(
                {
                    "game_slug":
                        prepared_launch.game_slug,
                    "launcher_type":
                        prepared_launch.launcher_type,
                    "launcher_game_id":
                        prepared_launch.launcher_game_id,
                    # Preserve KG-001 state keys while the
                    # backend schema evolves to launch profiles.
                    "launcher":
                        prepared_launch.launcher_type,
                    "launcher_app_id":
                        prepared_launch.launcher_game_id,
                    "game":
                        prepared_launch.game,
                    "launch_info":
                        launch_info,
                }
            )

        _write_state(state_file, state)

        result: dict[str, Any] = {
            "runtime_id": runtime_id,
            "deployment_stage": "stream_ready",
            "connection_info":
                _connection_info(runtime_id),
            "gpu": validation["gpu"],
            "interactive_session": interactive_session,
        }

        if display_policy_result is not None:
            result["display_policy"] = (
                display_policy_result
            )

        if (
            prepared_launch is not None
            and launch_info is not None
        ):
            result["game"] = prepared_launch.game
            result["launch_info"] = launch_info

        return JobExecutionResult(
            "succeeded",
            result,
        )
    except (GamingRuntimeError, GameLaunchError) as exc:
        return JobExecutionResult("blocked", {}, str(exc))


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
        state = _read_state(state_file)
        if state is None:
            if action == "delete":
                return JobExecutionResult(
                    "succeeded",
                    {"runtime_id": runtime_id, "deleted": True, "idempotent": True},
                )
            raise GamingRuntimeError("Gaming runtime does not exist on this node.")

        if action in {"stop", "delete"}:
            paired_clients = [
                item
                for item in state.get("paired_clients", [])
                if isinstance(item, dict)
            ]

            for client in paired_clients:
                client_uuid = str(
                    client.get("sunshine_client_uuid") or ""
                )

                if client_uuid:
                    unpair_client(
                        client_uuid=client_uuid,
                        api_url=sunshine_api_url,
                        username=sunshine_api_username,
                        password=sunshine_api_password,
                        verify_tls=sunshine_verify_tls,
                    )

            state["paired_clients"] = []

        if action == "delete":
            try:
                state_file.unlink()
            except FileNotFoundError:
                pass
            return JobExecutionResult(
                "succeeded",
                {"runtime_id": runtime_id, "deleted": True},
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

        interactive_session: dict[str, Any] | None = None

        if desired == "running":
            interactive_session = (
                _interactive_session_context()
            )
            state["interactive_session"] = (
                interactive_session
            )

        if state.get("status") == desired:
            return JobExecutionResult(
                "succeeded",
                {
                    "runtime_id": runtime_id,
                    "status": desired,
                    "idempotent": True,
                    **(
                        {
                            "connection_info":
                                _connection_info(runtime_id),
                            "deployment_stage":
                                "stream_ready",
                            "interactive_session":
                                interactive_session,
                        }
                        if desired == "running"
                        else {
                            "deployment_stage":
                                "stopped",
                        }
                    ),
                },
            )

        state["status"] = desired
        state["runtime_stage"] = (
            "stream_ready"
            if desired == "running"
            else "stopped"
        )
        _write_state(state_file, state)

        result: dict[str, Any] = {
            "runtime_id": runtime_id,
            "status": desired,
            "deployment_stage": state["runtime_stage"],
        }

        if desired == "running":
            result["connection_info"] = (
                _connection_info(runtime_id)
            )
            result["interactive_session"] = (
                interactive_session
            )
        return JobExecutionResult("succeeded", result)
    except (
        GamingRuntimeError,
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
