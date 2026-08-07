from pathlib import Path

import pytest

from khan_agent.client import ControlPlaneClient
from khan_agent.config import AgentSettings
from khan_agent.credentials import NodeCredentials


def settings_for(tmp_path: Path) -> AgentSettings:
    return AgentSettings.model_validate({
        "agent": {
            "node_name": "KC-TEST",
            "control_plane_url": "http://127.0.0.1:8000",
            "state_directory": str(tmp_path),
        },
        "security": {"verify_tls": False},
    })


class FakeResponse:
    def raise_for_status(self): pass
    def json(self): return {"id": "event"}


class FakeAsyncClient:
    calls = []
    def __init__(self, **kwargs): self.kwargs = kwargs
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def post(self, url, **kwargs):
        self.__class__.calls.append((url, kwargs))
        return FakeResponse()


@pytest.mark.asyncio
async def test_telemetry_uses_node_credentials(monkeypatch, tmp_path) -> None:
    FakeAsyncClient.calls = []
    monkeypatch.setattr("khan_agent.client.httpx.AsyncClient", FakeAsyncClient)
    client = ControlPlaneClient(settings_for(tmp_path))
    await client.report_installation_event(
        {"transaction_id": "tx", "status": "running", "stage": "preflight"},
        NodeCredentials(node_id="node-1", node_secret="secret-1"),
    )
    url, kwargs = FakeAsyncClient.calls[-1]
    assert url.endswith("/api/v1/nodes/installation-events")
    assert kwargs["headers"] == {
        "X-Node-ID": "node-1",
        "X-Node-Secret": "secret-1",
    }
