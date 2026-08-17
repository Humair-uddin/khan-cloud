from __future__ import annotations

import json
import os
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
from khan_agent.virtualization import JobExecutionResult


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


def create_session(
    payload: dict[str, Any],
    *,
    state_root: Path,
    execution_backend: str,
    streaming_backend: str,
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
        existing = _read_state(state_file)
        if existing is not None:
            if str(existing.get("gpu_uuid")) != gpu_uuid:
                raise GamingRuntimeError(
                    "Existing runtime is bound to a different GPU; refusing reassignment."
                )
            validation = _validate_windows_native(
                gpu_uuid=gpu_uuid,
                minimum_vram_mb=minimum_vram_mb,
                execution_backend=execution_backend,
                streaming_backend=streaming_backend,
            )
            # Idempotent create must never resurrect or otherwise
            # mutate an existing session's lifecycle state. A delayed
            # duplicate create can arrive after a legitimate stop.
            existing["gpu"] = validation["gpu"]
            _write_state(state_file, existing)

            result: dict[str, Any] = {
                "runtime_id": runtime_id,
                "status": str(existing.get("status") or "unknown"),
                "idempotent": True,
            }

            if existing.get("status") == "running":
                result["connection_info"] = _connection_info(runtime_id)

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
        }

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
            "connection_info":
                _connection_info(runtime_id),
            "gpu": validation["gpu"],
        }

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
        if state.get("status") == desired:
            return JobExecutionResult(
                "succeeded",
                {
                    "runtime_id": runtime_id,
                    "status": desired,
                    "idempotent": True,
                    **(
                        {"connection_info": _connection_info(runtime_id)}
                        if desired == "running"
                        else {}
                    ),
                },
            )

        state["status"] = desired
        _write_state(state_file, state)
        result: dict[str, Any] = {"runtime_id": runtime_id, "status": desired}
        if desired == "running":
            result["connection_info"] = _connection_info(runtime_id)
        return JobExecutionResult("succeeded", result)
    except (GamingRuntimeError, ValueError) as exc:
        return JobExecutionResult("blocked", {}, str(exc))
