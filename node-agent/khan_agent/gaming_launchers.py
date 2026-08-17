from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

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


class LauncherAdapter(Protocol):
    launcher_type: str

    def prepare(
        self,
        *,
        game_slug: str,
        launcher_game_id: str,
    ) -> PreparedGameLaunch:
        ...

    def launch(
        self,
        prepared: PreparedGameLaunch,
    ) -> dict[str, Any]:
        ...


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

    def launch(
        self,
        prepared: PreparedGameLaunch,
    ) -> dict[str, Any]:
        try:
            return launch_steam_app(
                Path(prepared.launcher_executable),
                prepared.launcher_game_id,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise GameLaunchError(
                f"Steam failed to launch AppID "
                f"{prepared.launcher_game_id}."
            ) from exc


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
) -> dict[str, Any]:
    adapter = _ADAPTERS.get(prepared.launcher_type)

    if adapter is None:
        raise GameLaunchError(
            f"Unsupported gaming launcher: "
            f"{prepared.launcher_type}."
        )

    result = dict(adapter.launch(prepared))

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
