from __future__ import annotations

from typing import Any

from khan_agent.windows_verified_process import (
    WindowsVerifiedProcessError,
    make_verified_process_ownership,
    snapshot_game_processes,
)


class WindowsWorkloadObserverError(RuntimeError):
    pass


def _identity_key(value: dict[str, Any]) -> tuple[int, int]:
    try:
        return (
            int(value["pid"]),
            int(value["creation_time_100ns"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WindowsWorkloadObserverError(
            "Workload process identity is incomplete."
        ) from exc


def make_workload_observation_authority(
    *,
    runtime_id: str,
    install_root: str,
    expected_session_id: int,
    launcher_type: str,
    launcher_game_id: str,
    baseline: list[dict[str, Any]],
) -> dict[str, Any]:
    if not str(runtime_id or "").strip():
        raise WindowsWorkloadObserverError(
            "Workload observation requires runtime_id."
        )

    if not str(install_root or "").strip():
        raise WindowsWorkloadObserverError(
            "Workload observation requires install_root."
        )

    if int(expected_session_id) <= 0:
        raise WindowsWorkloadObserverError(
            "Workload observation requires a managed Windows session."
        )

    return {
        "schema_version": 1,
        "authority_type": "customer_game_workload_observation",
        "runtime_id": str(runtime_id),
        "install_root": str(install_root),
        "interactive_session_id": int(expected_session_id),
        "launcher_type": str(launcher_type),
        "launcher_game_id": str(launcher_game_id),
        "baseline": [
            dict(value)
            for value in baseline
        ],
    }


def discover_customer_workload_processes(
    authority: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(authority, dict):
        raise WindowsWorkloadObserverError(
            "Workload observation authority is invalid."
        )

    if (
        str(authority.get("authority_type") or "")
        != "customer_game_workload_observation"
    ):
        raise WindowsWorkloadObserverError(
            "Unsupported workload observation authority."
        )

    try:
        schema_version = int(
            authority.get("schema_version") or 0
        )
        expected_session_id = int(
            authority.get("interactive_session_id") or 0
        )
    except (TypeError, ValueError):
        schema_version = 0
        expected_session_id = 0

    install_root = str(
        authority.get("install_root") or ""
    ).strip()

    baseline = authority.get("baseline")

    if (
        schema_version != 1
        or not str(authority.get("runtime_id") or "").strip()
        or not install_root
        or expected_session_id <= 0
        or not isinstance(baseline, list)
    ):
        raise WindowsWorkloadObserverError(
            "Workload observation authority is incomplete."
        )

    baseline_keys = {
        _identity_key(value)
        for value in baseline
        if isinstance(value, dict)
    }

    try:
        current = snapshot_game_processes(
            install_root=install_root,
            expected_session_id=expected_session_id,
        )
    except WindowsVerifiedProcessError as exc:
        raise WindowsWorkloadObserverError(
            "Customer workload discovery failed."
        ) from exc

    return [
        dict(value)
        for value in current
        if _identity_key(value) not in baseline_keys
    ]


def adopt_customer_workload(
    authority: dict[str, Any],
    processes: list[dict[str, Any]],
) -> dict[str, Any]:
    if not processes:
        raise WindowsWorkloadObserverError(
            "Customer workload adoption requires at least one process."
        )

    try:
        ownership = make_verified_process_ownership(
            runtime_id=str(authority["runtime_id"]),
            install_root=str(authority["install_root"]),
            expected_session_id=int(
                authority["interactive_session_id"]
            ),
            launcher_type=str(authority["launcher_type"]),
            launcher_game_id=str(
                authority["launcher_game_id"]
            ),
            processes=[
                dict(value)
                for value in processes
            ],
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        WindowsVerifiedProcessError,
    ) as exc:
        raise WindowsWorkloadObserverError(
            "Customer workload could not be adopted safely."
        ) from exc

    ownership["workload_observation"] = {
        "authority_type": str(
            authority["authority_type"]
        ),
        "schema_version": int(
            authority["schema_version"]
        ),
    }

    return ownership
