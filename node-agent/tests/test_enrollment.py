from pathlib import Path

import pytest

from khan_agent.config import AgentSettings
from khan_agent.runtime import AgentRuntime


class FakeClient:
    async def enroll(self, payload):
        assert payload["machine_id"]
        assert payload["hostname"]
        return {
            "node_id": "11111111-1111-1111-1111-111111111111",
            "node_secret": "generated-secret",
            "status": "online",
        }

    async def heartbeat(self, payload, credentials):
        assert credentials.node_secret == "generated-secret"
        return {
            "status": "online",
            "last_seen_at": "2026-08-05T00:00:00Z",
        }


def settings_for(tmp_path: Path) -> AgentSettings:
    return AgentSettings.model_validate(
        {
            "agent": {
                "node_name": "KC-TEST-NODE",
                "control_plane_url": "http://127.0.0.1:8000",
                "state_directory": str(tmp_path),
                "plugin_directory": str(tmp_path / "plugins"),
            },
            "security": {"enrollment_token": "test-token", "verify_tls": False},
        }
    )


@pytest.mark.asyncio
async def test_enroll_then_heartbeat(tmp_path) -> None:
    runtime = AgentRuntime(settings_for(tmp_path))
    runtime.client = FakeClient()

    await runtime.enroll_once()
    assert runtime.credential_store.exists()

    await runtime.heartbeat_once()
