from pathlib import Path

import pytest

from khan_agent.client import ControlPlaneClient
from khan_agent.config import AgentSettings


def settings_for(tmp_path: Path, *, deployment_code: str = "", legacy: str = "") -> AgentSettings:
    return AgentSettings.model_validate({
        "agent": {
            "node_name": "KC-TEST",
            "control_plane_url": "http://127.0.0.1:8000",
            "state_directory": str(tmp_path),
        },
        "security": {
            "deployment_enrollment_code": deployment_code,
            "enrollment_token": legacy,
            "verify_tls": False,
        },
    })


class FakeResponse:
    def raise_for_status(self):
        pass
    def json(self):
        return {"node_id": "n", "node_secret": "s"}


class FakeAsyncClient:
    calls = []
    def __init__(self, **kwargs):
        self.kwargs = kwargs
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def post(self, url, **kwargs):
        self.__class__.calls.append((url, kwargs))
        return FakeResponse()


@pytest.mark.asyncio
async def test_deployment_code_is_preferred(monkeypatch, tmp_path) -> None:
    FakeAsyncClient.calls = []
    monkeypatch.setattr("khan_agent.client.httpx.AsyncClient", FakeAsyncClient)
    client = ControlPlaneClient(settings_for(tmp_path, deployment_code="kcdep_test", legacy="legacy"))
    await client.enroll({"machine_id": "m"})
    headers = FakeAsyncClient.calls[-1][1]["headers"]
    assert headers == {"X-Deployment-Enrollment-Code": "kcdep_test"}


@pytest.mark.asyncio
async def test_legacy_token_remains_fallback(monkeypatch, tmp_path) -> None:
    FakeAsyncClient.calls = []
    monkeypatch.setattr("khan_agent.client.httpx.AsyncClient", FakeAsyncClient)
    client = ControlPlaneClient(settings_for(tmp_path, legacy="legacy"))
    await client.enroll({"machine_id": "m"})
    headers = FakeAsyncClient.calls[-1][1]["headers"]
    assert headers == {"X-Enrollment-Token": "legacy"}


@pytest.mark.asyncio
async def test_missing_enrollment_credential_is_rejected(tmp_path) -> None:
    client = ControlPlaneClient(settings_for(tmp_path))
    with pytest.raises(RuntimeError, match="Enrollment credential is missing"):
        await client.enroll({"machine_id": "m"})
