from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from khan_agent.gaming_backends import locate_sunshine


def _acf_value(text: str, key: str) -> str:
    match = re.search(r'^\s*"' + re.escape(key) + r'"\s+"([^"]*)"', text, flags=re.MULTILINE | re.IGNORECASE)
    return match.group(1) if match else ""


def _steam_roots() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / "Steam")
    candidates.extend([Path.home() / ".steam" / "steam", Path.home() / ".local" / "share" / "Steam"])
    result: list[Path] = []
    for path in candidates:
        if path.exists() and path not in result:
            result.append(path)
    return result


def _steam_libraries(root: Path) -> list[Path]:
    libraries = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if not vdf.exists():
        return libraries
    text = vdf.read_text(encoding="utf-8", errors="ignore")
    for raw in re.findall(r'"path"\s+"([^"]+)"', text, flags=re.IGNORECASE):
        path = Path(raw.replace(chr(92) * 2, chr(92)))
        if path.exists() and path not in libraries:
            libraries.append(path)
    return libraries


def collect_steam_inventory() -> dict[str, Any]:
    roots = _steam_roots()
    games: list[dict[str, Any]] = []
    library_paths: list[str] = []
    seen: set[str] = set()
    for root in roots:
        for library in _steam_libraries(root):
            library_paths.append(str(library))
            steamapps = library / "steamapps"
            if not steamapps.exists():
                continue
            for manifest in steamapps.glob("appmanifest_*.acf"):
                text = manifest.read_text(encoding="utf-8", errors="ignore")
                app_id = _acf_value(text, "appid") or manifest.stem.removeprefix("appmanifest_")
                if not app_id or app_id in seen:
                    continue
                seen.add(app_id)
                install_dir = _acf_value(text, "installdir")
                games.append({"launcher": "steam", "app_id": app_id, "name": _acf_value(text, "name"), "installed": True, "state": "installed", "build_id": _acf_value(text, "buildid"), "install_path": str(steamapps / "common" / install_dir) if install_dir else "", "manifest_path": str(manifest)})
    return {"installed": bool(roots), "roots": [str(path) for path in roots], "libraries": sorted(set(library_paths)), "games": games}


def collect_interactive_session() -> dict[str, Any]:
    if platform.system() != "Windows":
        return {
            "available": False,
            "session_id": None,
            "username": "",
        }

    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        (
            "$p = Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -eq 'explorer.exe' } | "
            "Select-Object -First 1; "
            "if ($null -eq $p) { exit 3 }; "
            "$o = $p | Invoke-CimMethod -MethodName GetOwner; "
            "Write-Output ($p.SessionId.ToString() + '|' + "
            "$o.Domain + [char]92 + $o.User)"
        ),
    ]

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "available": False,
            "session_id": None,
            "username": "",
        }

    if result.returncode != 0:
        return {
            "available": False,
            "session_id": None,
            "username": "",
        }

    raw = result.stdout.strip().splitlines()
    if not raw:
        return {
            "available": False,
            "session_id": None,
            "username": "",
        }

    parts = raw[-1].split("|", 1)
    if len(parts) != 2:
        return {
            "available": False,
            "session_id": None,
            "username": "",
        }

    try:
        session_id = int(parts[0])
    except ValueError:
        return {
            "available": False,
            "session_id": None,
            "username": "",
        }

    return {
        "available": session_id > 0,
        "session_id": session_id,
        "username": parts[1].strip(),
    }


def collect_gaming_inventory() -> dict[str, Any]:
    steam = collect_steam_inventory()
    sunshine = locate_sunshine()
    return {
        "launchers": {
            "steam": {
                key: value
                for key, value in steam.items()
                if key != "games"
            }
        },
        "games": steam["games"],
        "streaming": {
            "sunshine": {
                "installed": bool(sunshine),
                "ready": bool(sunshine),
                "executable": str(sunshine) if sunshine else "",
            }
        },
        "interactive_session": collect_interactive_session(),
    }
