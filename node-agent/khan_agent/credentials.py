from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class NodeCredentials:
    node_id: str
    node_secret: str


class CredentialStore:
    def __init__(self, state_directory: Path) -> None:
        self.path = state_directory / "credentials.json"

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> NodeCredentials:
        data = json.loads(self.path.read_text())
        return NodeCredentials(**data)

    def save(self, credentials: NodeCredentials) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(credentials), indent=2))
        temp.chmod(0o600)
        temp.replace(self.path)
        self.path.chmod(0o600)
