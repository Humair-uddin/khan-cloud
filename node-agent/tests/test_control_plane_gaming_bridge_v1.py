from pathlib import Path
from uuid import uuid4

import pytest

from khan_agent.config import AgentSettings
from khan_agent.credentials import NodeCredentials
from khan_agent.runtime import AgentRuntime


def _settings(tmp_path: Path) -> AgentSettings:
    return AgentSettings.model_validate(
        {
            "agent": {
                "node_name": "KC-GAMING-BRIDGE",
                "control_plane_url": "http://127.0.0.1:8000",
                "state_directory": str(tmp_path),
                "plugin_directory": str(tmp_path / "plugins"),
            },
            "gaming": {
                "enabled": True,
                "execution_backend": "windows_native",
                "streaming_backend": "sunshine",
            },
        }
    )


class FakeClient:
    def __init__(self, job):
        self.job = job
        self.reports = []

    async def next_job(self, credentials):
        assert credentials.node_secret == "secret"
        job, self.job = self.job, None
        return job

    async def report_job_result(self, job_id, payload, credentials):
        assert credentials.node_id == "node-1"
        self.reports.append((job_id, payload))
        return {"id": job_id, **payload}


@pytest.mark.asyncio
async def test_agent_bridges_gaming_job_result_to_control_plane(
    tmp_path,
    monkeypatch,
):
    from khan_agent import gaming_runtime

    session_id = uuid4()
    job_id = uuid4()
    job = {
        "id": str(job_id),
        "job_type": "gaming.session.create",
        "payload": {
            "session_id": str(session_id),
            "gpu_uuid": "GPU-A",
            "minimum_vram_mb": 8192,
        },
    }

    class ManagedSession:
        session_id = 1
        available = True
        source = "test"
        managed = True
        username = "KhanGaming"
        broker_mode = "managed_autologon"

    monkeypatch.setattr(
        gaming_runtime,
        "require_interactive_session",
        lambda **kwargs: ManagedSession(),
    )

    monkeypatch.setattr(
        gaming_runtime,
        "locate_sunshine",
        lambda: Path(r"C:\\Program Files\\Sunshine\\sunshine.exe"),
    )
    monkeypatch.setattr(
        gaming_runtime,
        "probe_sunshine_readiness",
        lambda **kwargs: {
            "ready": True,
            "authenticated_api": True,
            "endpoint": "/api/clients/list",
        },
    )
    monkeypatch.setattr(
        gaming_runtime,
        "probe_nvidia_gpu",
        lambda gpu_uuid: {
            "available": True,
            "uuid": gpu_uuid,
            "name": "NVIDIA RTX Test",
            "memory_total_mib": 12288,
            "driver_version": "test",
        },
    )
    monkeypatch.setattr(
        gaming_runtime,
        "secure_private_file",
        lambda path: None,
    )

    runtime = AgentRuntime(_settings(tmp_path))
    client = FakeClient(job)
    runtime.client = client

    await runtime._process_one_node_job(
        NodeCredentials("node-1", "secret")
    )

    assert len(client.reports) == 1
    reported_id, payload = client.reports[0]
    assert reported_id == str(job_id)
    assert payload["status"] == "succeeded"
    assert payload["result"]["runtime_id"] == (
        f"kc-gaming-{session_id}"
    )
    assert payload["result"]["connection_info"]["ready"] is True


@pytest.mark.asyncio
async def test_unhandled_executor_failure_is_reported_not_lost(
    tmp_path,
    monkeypatch,
):
    job_id = uuid4()
    job = {
        "id": str(job_id),
        "job_type": "gaming.session.start",
        "payload": {"session_id": str(uuid4())},
    }

    runtime = AgentRuntime(_settings(tmp_path))
    client = FakeClient(job)
    runtime.client = client

    monkeypatch.setattr(
        "khan_agent.runtime.execute_node_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("boom")
        ),
    )

    await runtime._process_one_node_job(
        NodeCredentials("node-1", "secret")
    )

    assert len(client.reports) == 1
    _, payload = client.reports[0]
    assert payload["status"] == "failed"
    assert payload["result"] == {}
    assert payload["error_message"] == (
        "Node job execution failed unexpectedly."
    )
