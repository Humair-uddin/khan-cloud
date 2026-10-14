from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import platform
from typing import Any, Protocol

from khan_agent.launch_diagnostics import LaunchTrace

# Steam launch requests are asynchronous. Production launch latency can
# exceed the generic verified-process discovery window, so Steam owns a
# separate bounded observation policy without weakening process identity.
_STEAM_BROKER_PROCESS_TIMEOUT_SECONDS = 120.0

from khan_agent.gaming_backends import locate_steam, launch_steam_app
from khan_agent.gaming_inventory import collect_steam_inventory


class GameLaunchError(RuntimeError):
    """Safe, user-facing game launch preparation/execution failure."""


@dataclass(frozen=True)
class PreparedGameLaunch:
    game_slug: str
    launcher_type: str
    launcher_game_id: str
    game: dict[str, Any]
    launcher_executable: str
    runtime_id: str = ""
    expected_session_id: int | None = None
    presentation_contract: dict[str, Any] | None = None


class LauncherAdapter(Protocol):
    launcher_type: str

    def prepare(
        self,
        *,
        game_slug: str,
        launcher_game_id: str,
    ) -> PreparedGameLaunch:
        ...

    def build_launch_attempt_authority(
        self,
        prepared: PreparedGameLaunch,
    ) -> dict[str, Any] | None:
        ...

    def launch(
        self,
        prepared: PreparedGameLaunch,
    ) -> dict[str, Any]:
        ...

    def dispatch(
        self,
        prepared: PreparedGameLaunch,
        *,
        launch_attempt: dict[str, Any],
    ) -> dict[str, Any]:
        ...


def _game_launch_arguments(
    prepared: PreparedGameLaunch,
) -> tuple[str, ...]:
    """
    Resolve game-specific process arguments from presentation facts
    already verified before launch.

    Launcher backends remain game-agnostic.  No resolution is invented:
    CS2 receives explicit display arguments only when Khan Cloud has a
    verified positive-width/height presentation contract.
    """
    if prepared.game_slug != "counter-strike-2":
        return ()

    contract = prepared.presentation_contract

    if not isinstance(contract, dict):
        return ()

    if contract.get("verified") is not True:
        return ()

    width = contract.get("width")
    height = contract.get("height")

    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or width <= 0
    ):
        return ()

    if (
        not isinstance(height, int)
        or isinstance(height, bool)
        or height <= 0
    ):
        return ()

    return (
        "-w",
        str(width),
        "-h",
        str(height),
        "-windowed",
        "-noborder",
    )


class SteamLauncherAdapter:
    launcher_type = "steam"

    def prepare(
        self,
        *,
        game_slug: str,
        launcher_game_id: str,
    ) -> PreparedGameLaunch:
        app_id = str(launcher_game_id).strip()

        if not app_id.isdigit() or int(app_id) <= 0:
            raise GameLaunchError(
                "Steam launcher_game_id must be a positive AppID."
            )

        inventory = collect_steam_inventory()

        installed_game = next(
            (
                game
                for game in inventory.get("games", [])
                if str(game.get("launcher") or "").lower()
                == "steam"
                and str(game.get("app_id") or "") == app_id
                and bool(game.get("installed"))
            ),
            None,
        )

        if installed_game is None:
            raise GameLaunchError(
                f"Steam AppID {app_id} is not installed "
                "on this gaming node."
            )

        steam = locate_steam()

        if steam is None:
            raise GameLaunchError(
                "Steam is not available; Khan Cloud will not "
                "install or replace it automatically."
            )

        return PreparedGameLaunch(
            game_slug=game_slug,
            launcher_type=self.launcher_type,
            launcher_game_id=app_id,
            game=dict(installed_game),
            launcher_executable=str(steam),
        )

    def build_launch_attempt_authority(
        self,
        prepared: PreparedGameLaunch,
    ) -> dict[str, Any] | None:
        if (
            not prepared.runtime_id
            or platform.system() != "Windows"
            or prepared.expected_session_id is None
        ):
            return None

        install_root = str(
            prepared.game.get("install_path") or ""
        ).strip()

        if not install_root:
            raise GameLaunchError(
                "Steam brokered ownership requires the "
                "verified installed game path."
            )

        from khan_agent.windows_verified_process import (
            make_launch_attempt_authority,
            snapshot_game_processes,
        )

        baseline = snapshot_game_processes(
            install_root=install_root,
            expected_session_id=int(
                prepared.expected_session_id
            ),
        )

        authority = make_launch_attempt_authority(
            runtime_id=prepared.runtime_id,
            install_root=install_root,
            expected_session_id=int(
                prepared.expected_session_id
            ),
            launcher_type=self.launcher_type,
            launcher_game_id=prepared.launcher_game_id,
            baseline=baseline,
        )
        LaunchTrace(
            authority.get("attempt_id", ""), prepared.runtime_id
        ).emit("attempt_baseline_created", baseline_count=len(baseline))
        return authority

    def dispatch(
        self,
        prepared: PreparedGameLaunch,
        *,
        launch_attempt: dict[str, Any],
    ) -> dict[str, Any]:
        """Submit one Steam broker request without adopting the game.

        The caller must persist launch-attempt authority before entering
        this method. Discovery and verified ownership remain exclusively
        with the customer-workload observer.
        """
        if (
            not prepared.runtime_id
            or platform.system() != "Windows"
            or prepared.expected_session_id is None
        ):
            raise GameLaunchError(
                "Customer PLAY requires a managed Windows runtime."
            )

        install_root = str(
            prepared.game.get("install_path") or ""
        ).strip()
        if not install_root:
            raise GameLaunchError(
                "Steam PLAY requires the verified installed game path."
            )

        try:
            schema_version = int(
                launch_attempt.get("schema_version") or 0
            )
            expected_session_id = int(
                launch_attempt.get("interactive_session_id") or 0
            )
        except (TypeError, ValueError):
            schema_version = 0
            expected_session_id = 0

        if (
            schema_version != 2
            or str(launch_attempt.get("authority_type") or "")
            != "steam_verified_process_launch_attempt"
            or not str(launch_attempt.get("attempt_id") or "").strip()
            or str(launch_attempt.get("runtime_id") or "")
            != prepared.runtime_id
            or str(launch_attempt.get("install_root") or "")
            != install_root
            or expected_session_id != int(prepared.expected_session_id)
            or str(launch_attempt.get("launcher_type") or "")
            != self.launcher_type
            or str(launch_attempt.get("launcher_game_id") or "")
            != prepared.launcher_game_id
            or not isinstance(launch_attempt.get("baseline"), list)
        ):
            raise GameLaunchError(
                "Persisted Steam PLAY authority does not match the "
                "prepared runtime."
            )

        request = dict(launch_steam_app(
            Path(prepared.launcher_executable),
            prepared.launcher_game_id,
            expected_session_id=prepared.expected_session_id,
            launch_arguments=_game_launch_arguments(prepared),
        ))
        request_ownership = request.pop("runtime_ownership", None)
        return {
            **request,
            "dispatch_only": True,
            "launch_request_ownership": (
                dict(request_ownership)
                if isinstance(request_ownership, dict)
                else {}
            ),
            "launcher_type": prepared.launcher_type,
            "launcher_game_id": prepared.launcher_game_id,
            "game_slug": prepared.game_slug,
            "launch_attempt_id": str(launch_attempt["attempt_id"]),
        }

    def launch(
        self,
        prepared: PreparedGameLaunch,
        *,
        launch_attempt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        trace = LaunchTrace(
            (launch_attempt or {}).get("attempt_id", ""),
            prepared.runtime_id,
        )
        trace.emit("steam_adapter_enter")
        try:
            if (
                prepared.runtime_id
                and platform.system() == "Windows"
                and prepared.expected_session_id is not None
            ):
                install_root = str(
                    prepared.game.get(
                        "install_path"
                    ) or ""
                ).strip()

                if not install_root:
                    raise GameLaunchError(
                        "Steam brokered ownership requires the "
                        "verified installed game path."
                    )

                from khan_agent.windows_verified_process import (
                    make_verified_process_ownership,
                    snapshot_game_processes,
                    wait_for_new_game_processes,
                )

                if launch_attempt is not None:
                    if (
                        str(
                            launch_attempt.get(
                                "authority_type"
                            ) or ""
                        )
                        != "steam_verified_process_launch_attempt"
                        or str(
                            launch_attempt.get(
                                "runtime_id"
                            ) or ""
                        )
                        != prepared.runtime_id
                        or str(
                            launch_attempt.get(
                                "install_root"
                            ) or ""
                        )
                        != install_root
                        or int(
                            launch_attempt.get(
                                "interactive_session_id"
                            ) or 0
                        )
                        != int(
                            prepared.expected_session_id
                        )
                        or str(
                            launch_attempt.get(
                                "launcher_type"
                            ) or ""
                        )
                        != self.launcher_type
                        or str(
                            launch_attempt.get(
                                "launcher_game_id"
                            ) or ""
                        )
                        != prepared.launcher_game_id
                        or not isinstance(
                            launch_attempt.get("baseline"),
                            list,
                        )
                    ):
                        raise GameLaunchError(
                            "Persisted Steam launch-attempt "
                            "authority does not match the "
                            "prepared runtime."
                        )

                    baseline = [
                        dict(value)
                        for value in launch_attempt["baseline"]
                        if isinstance(value, dict)
                    ]
                else:
                    baseline = snapshot_game_processes(
                        install_root=install_root,
                        expected_session_id=int(
                            prepared.expected_session_id
                        ),
                    )

                # Steam is already running inside the managed interactive
                # session.  This transient steam.exe -applaunch process is
                # only a broker request; it is not the customer workload
                # lifetime boundary.  Do not place the request carrier in
                # the D1 Job Object.  The resulting game process is adopted
                # only after session/install-root/creation identity
                # verification below.
                trace.emit("launcher_request_begin")
                request = launch_steam_app(
                    Path(prepared.launcher_executable),
                    prepared.launcher_game_id,
                    expected_session_id=prepared.expected_session_id,
                    launch_arguments=_game_launch_arguments(prepared),
                )

                trace.emit(
                    "launcher_request_returned",
                    request_pid=request.get("launcher_pid"),
                )
                request_ownership = dict(
                    request.get(
                        "runtime_ownership"
                    ) or {}
                )

                trace.emit("verified_discovery_begin")
                processes = wait_for_new_game_processes(
                    install_root=install_root,
                    expected_session_id=int(
                        prepared.expected_session_id
                    ),
                    baseline=baseline,
                    attempt_id=trace.attempt_id,
                    runtime_id=prepared.runtime_id,
                    timeout_seconds=(
                        _STEAM_BROKER_PROCESS_TIMEOUT_SECONDS
                    ),
                )

                trace.emit(
                    "verified_discovery_end",
                    process_count=len(processes),
                    pids=[int(p["pid"]) for p in processes[:16]],
                )
                runtime_ownership = (
                    make_verified_process_ownership(
                        runtime_id=prepared.runtime_id,
                        install_root=install_root,
                        expected_session_id=int(
                            prepared.expected_session_id
                        ),
                        launcher_type=self.launcher_type,
                        launcher_game_id=(
                            prepared.launcher_game_id
                        ),
                        processes=processes,
                        launch_request_ownership=(
                            request_ownership
                            if request_ownership
                            else None
                        ),
                    )
                )

                trace.emit(
                    "ownership_construction_complete",
                    process_count=len(processes),
                )

                # The transient steam.exe -applaunch process is launch
                # authority, not the customer workload lifetime.
                # Preserve it separately for audit while launcher_pid
                # becomes the primary verified game identity.
                result = dict(request)
                result[
                    "launch_request_pid"
                ] = result.get("launcher_pid")
                result[
                    "launch_request_ownership"
                ] = request_ownership
                result[
                    "launcher_pid"
                ] = int(processes[0]["pid"])
                result[
                    "runtime_ownership"
                ] = runtime_ownership
                result[
                    "ownership_mode"
                ] = "steam_brokered_verified_process"

                return result

            if prepared.runtime_id:
                return launch_steam_app(
                    Path(prepared.launcher_executable),
                    prepared.launcher_game_id,
                    runtime_id=prepared.runtime_id,
                    expected_session_id=prepared.expected_session_id,
                    launch_arguments=_game_launch_arguments(prepared),
                )

            # Preserve the frozen KG-002 adapter signature for
            # legacy callers and tests. D1-owned production
            # sessions always carry runtime_id.
            return launch_steam_app(
                Path(prepared.launcher_executable),
                prepared.launcher_game_id,
            )
        except GameLaunchError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise GameLaunchError(
                f"Steam failed to launch AppID "
                f"{prepared.launcher_game_id}."
            ) from exc


def build_prepared_launch_attempt_authority(
    prepared: PreparedGameLaunch,
) -> dict[str, Any] | None:
    adapter = _ADAPTERS.get(
        str(prepared.launcher_type).strip().lower()
    )

    if adapter is None:
        raise GameLaunchError(
            f"Unsupported launcher type: {prepared.launcher_type}."
        )

    builder = getattr(
        adapter,
        "build_launch_attempt_authority",
        None,
    )

    if builder is None:
        return None

    return builder(prepared)


def dispatch_prepared_game(
    prepared: PreparedGameLaunch,
    *,
    launch_attempt: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch a launcher request; never discover or adopt a workload."""
    adapter = _ADAPTERS.get(
        str(prepared.launcher_type).strip().lower()
    )
    if adapter is None:
        raise GameLaunchError(
            f"Unsupported launcher type: {prepared.launcher_type}."
        )

    dispatcher = getattr(adapter, "dispatch", None)
    if dispatcher is None:
        raise GameLaunchError(
            f"Launcher {prepared.launcher_type} does not support PLAY."
        )

    return dict(
        dispatcher(
            prepared,
            launch_attempt=launch_attempt,
        )
    )



_ADAPTERS: dict[str, LauncherAdapter] = {
    "steam": SteamLauncherAdapter(),
}


def supported_launcher_types() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def prepare_game_launch(
    payload: dict[str, Any],
) -> PreparedGameLaunch | None:
    """
    Convert a control-plane launch identity into locally verified launch data.

    Generic gaming sessions remain backward compatible: when no game/launcher
    metadata is supplied, no game process is launched.

    Both legacy KG-001 names and future generic names are accepted:
        launcher / launcher_type
        launcher_app_id / launcher_game_id
    """

    game_slug = str(
        payload.get("game_slug") or ""
    ).strip()

    launcher_type = str(
        payload.get("launcher_type")
        or payload.get("launcher")
        or ""
    ).strip().lower()

    launcher_game_id = str(
        payload.get("launcher_game_id")
        or payload.get("launcher_app_id")
        or ""
    ).strip()

    if not game_slug and not launcher_type and not launcher_game_id:
        return None

    if not game_slug:
        raise GameLaunchError(
            "Game launch metadata requires game_slug."
        )

    if not launcher_type:
        raise GameLaunchError(
            "Game launch metadata requires launcher_type."
        )

    if not launcher_game_id:
        raise GameLaunchError(
            "Game launch metadata requires launcher_game_id."
        )

    adapter = _ADAPTERS.get(launcher_type)

    if adapter is None:
        raise GameLaunchError(
            f"Unsupported gaming launcher: {launcher_type}."
        )

    return adapter.prepare(
        game_slug=game_slug,
        launcher_game_id=launcher_game_id,
    )


def launch_prepared_game(
    prepared: PreparedGameLaunch,
    *,
    launch_attempt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trace = LaunchTrace(
        (launch_attempt or {}).get("attempt_id", ""),
        prepared.runtime_id,
    )
    trace.emit("launch_prepared_game_enter")
    adapter = _ADAPTERS.get(prepared.launcher_type)

    if adapter is None:
        raise GameLaunchError(
            f"Unsupported gaming launcher: "
            f"{prepared.launcher_type}."
        )

    if launch_attempt is not None:
        result = dict(
            adapter.launch(
                prepared,
                launch_attempt=launch_attempt,
            )
        )
    else:
        result = dict(adapter.launch(prepared))

    trace.emit("launcher_adapter_returned")
    # KG-009E: production Windows customer workloads must be
    # presented on Khan VDD rather than whichever physical monitor
    # Windows currently considers primary.  The presentation helper
    # runs only after the D1-owned launcher has been established.
    #
    # Presentation failure is deliberately returned as launch
    # metadata instead of raising here.  gaming_runtime can then fail
    # stream readiness through its existing cleanup path while still
    # retaining the canonical Job Object ownership proof.
    if (
        platform.system() == "Windows"
        and prepared.expected_session_id is not None
    ):
        install_root = str(
            prepared.game.get("install_path") or ""
        ).strip()

        if not install_root:
            result["presentation"] = {
                "required": True,
                "verified": False,
                "target_type": "khan_vdd",
                "reason": "game_install_path_unavailable",
            }
        else:
            try:
                from khan_agent.windows_presentation import (
                    ensure_game_on_vdd,
                )

                trace.emit("presentation_helper_begin")
                result["presentation"] = (
                    ensure_game_on_vdd(
                        install_root=install_root,
                        attempt_id=trace.attempt_id,
                        runtime_id=prepared.runtime_id,
                        authoritative_pid=int(
                            result["launcher_pid"]
                        ),
                        expected_session_id=int(
                            prepared.expected_session_id
                        ),
                    )
                )
                trace.emit(
                    "presentation_helper_returned",
                    verified=bool(result["presentation"].get("verified")),
                )
            except Exception as exc:
                trace.emit("presentation_helper_returned",
                           verified=False, error_type=type(exc).__name__)
                result["presentation"] = {
                    "required": True,
                    "verified": False,
                    "target_type": "khan_vdd",
                    "reason":
                        "presentation_verification_failed",
                    "error_type":
                        type(exc).__name__,
                    "error":
                        str(exc),
                }

    result.setdefault(
        "launcher_type",
        prepared.launcher_type,
    )
    result.setdefault(
        "launcher_game_id",
        prepared.launcher_game_id,
    )
    result.setdefault(
        "game_slug",
        prepared.game_slug,
    )

    return result
