from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from khan_agent.file_security import secure_private_file


def _clean(value: str) -> str:
    value = " ".join(str(value or "").strip().split())
    bad = {"", "none", "null", "unknown", "default string", "to be filled by o.e.m.", "system serial number"}
    return "" if value.lower() in bad else value


def _run(args: list[str]) -> str:
    try:
        cp = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
        return _clean(cp.stdout)
    except (OSError, subprocess.SubprocessError):
        return ""


def collect_hardware_identity() -> dict[str, str]:
    system = platform.system().lower()
    data = {"system_uuid": "", "serial_number": "", "manufacturer": "", "model": ""}
    if system == "windows":
        script = (
            "$c=Get-CimInstance Win32_ComputerSystemProduct;"
            "$b=Get-CimInstance Win32_BIOS;"
            "$s=Get-CimInstance Win32_ComputerSystem;"
            "[pscustomobject]@{system_uuid=$c.UUID;serial_number=$b.SerialNumber;"
            "manufacturer=$s.Manufacturer;model=$s.Model}|ConvertTo-Json -Compress"
        )
        raw = _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])
        try:
            obj = json.loads(raw)
            for key in data: data[key] = _clean(obj.get(key, ""))
        except (json.JSONDecodeError, TypeError):
            pass
    elif system == "linux":
        paths = {
            "system_uuid": "/sys/class/dmi/id/product_uuid",
            "serial_number": "/sys/class/dmi/id/product_serial",
            "manufacturer": "/sys/class/dmi/id/sys_vendor",
            "model": "/sys/class/dmi/id/product_name",
        }
        for key, name in paths.items():
            try: data[key] = _clean(Path(name).read_text())
            except OSError: pass
    return data


def hardware_fingerprint(evidence: dict[str, str]) -> str:
    stable = [
        _clean(evidence.get("system_uuid", "")).lower(),
        _clean(evidence.get("serial_number", "")).lower(),
        _clean(evidence.get("manufacturer", "")).lower(),
        _clean(evidence.get("model", "")).lower(),
    ]
    if not stable[0] and not stable[1]:
        return ""
    return hashlib.sha256("\x1f".join(stable).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NodeIdentity:
    node_uuid: str
    hostname: str
    platform: str
    platform_release: str
    machine: str
    hardware_fingerprint: str = ""
    system_uuid: str = ""
    serial_number: str = ""
    manufacturer: str = ""
    model: str = ""


class IdentityStore:
    def __init__(self, state_directory: Path) -> None:
        self.state_directory = state_directory
        self.path = state_directory / "identity.json"

    def load_or_create(self) -> NodeIdentity:
        self.state_directory.mkdir(parents=True, exist_ok=True)
        evidence = collect_hardware_identity()
        fingerprint = hardware_fingerprint(evidence)
        if self.path.exists():
            data = json.loads(self.path.read_text())
            # Upgrade old identity files without changing their deployment UUID.
            data.setdefault("hardware_fingerprint", fingerprint)
            for key, value in evidence.items(): data.setdefault(key, value)
            identity = NodeIdentity(**data)
            self.path.write_text(json.dumps(asdict(identity), indent=2))
            secure_private_file(self.path)
            return identity
        identity = NodeIdentity(
            node_uuid=str(uuid.uuid4()), hostname=socket.gethostname(),
            platform=platform.system().lower(), platform_release=platform.release(),
            machine=platform.machine(), hardware_fingerprint=fingerprint, **evidence,
        )
        self.path.write_text(json.dumps(asdict(identity), indent=2))
        secure_private_file(self.path)
        return identity
