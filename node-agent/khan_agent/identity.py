from __future__ import annotations

import json
import platform
import socket
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from khan_agent.file_security import secure_private_file


@dataclass(frozen=True)
class NodeIdentity:
    node_uuid: str
    hostname: str
    platform: str
    platform_release: str
    machine: str


class IdentityStore:
    def __init__(self, state_directory: Path) -> None:
        self.state_directory = state_directory
        self.path = state_directory / "identity.json"

    def load_or_create(self) -> NodeIdentity:
        self.state_directory.mkdir(parents=True, exist_ok=True)

        if self.path.exists():
            data = json.loads(self.path.read_text())
            return NodeIdentity(**data)

        identity = NodeIdentity(
            node_uuid=str(uuid.uuid4()),
            hostname=socket.gethostname(),
            platform=platform.system().lower(),
            platform_release=platform.release(),
            machine=platform.machine(),
        )
        self.path.write_text(json.dumps(asdict(identity), indent=2))
        secure_private_file(self.path)
        return identity
