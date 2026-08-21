from pathlib import Path
from uuid import uuid4

import pytest

from khan_agent import gaming_runtime
from khan_agent import sunshine_broker


class FakeResponse:
    def __init__(
        self,
        status_code=200,
        payload=None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.is_error = status_code >= 400

    def json(self):
        return self._payload


class FakeClient:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        return FakeResponse(200, {"success": True})

    def get(self, path):
        self.calls.append(("GET", path, None))
        return FakeResponse(
            200,
            {
                "clients": [
                    {
                        "uuid": "CLIENT-UUID",
                        "name": "KC-CLIENT",
                    }
                ]
            },
        )


def test_sunshine_pairing_uses_local_authenticated_api(
    monkeypatch,
):
    FakeClient.calls = []

    monkeypatch.setattr(
        sunshine_broker.httpx,
        "Client",
        FakeClient,
    )

    result = sunshine_broker.pair_client(
        pin="1234",
        client_name="KC-CLIENT",
        api_url="https://127.0.0.1:47990",
        username="local-admin",
        password="local-secret",
        verify_tls=False,
    )

    assert (
        result["sunshine_client_uuid"]
        == "CLIENT-UUID"
    )

    assert (
        "POST",
        "/api/pin",
        {
            "pin": "1234",
            "name": "KC-CLIENT",
        },
    ) in FakeClient.calls

    assert (
        "GET",
        "/api/clients/list",
        None,
    ) in FakeClient.calls


def test_runtime_pair_state_never_persists_pin(
    tmp_path,
    monkeypatch,
):
    session_id = uuid4()
    runtime_id = f"kc-gaming-{session_id}"

    state_file = (
        tmp_path
        / "sessions"
        / f"{runtime_id}.json"
    )
    state_file.parent.mkdir(parents=True)

    state_file.write_text(
        """{
  "session_id": "%s",
  "runtime_id": "%s",
  "status": "running",
  "paired_clients": []
}
""" % (session_id, runtime_id)
    )

    monkeypatch.setattr(
        gaming_runtime,
        "pair_client",
        lambda **kwargs: {
            "sunshine_client_uuid": "CLIENT-1",
            "client_name": kwargs["client_name"],
            "paired": True,
        },
    )

    result = gaming_runtime.pair_connection(
        {
            "session_id": str(session_id),
            "pin": "1234",
            "client_name": "KC-CLIENT",
        },
        state_root=tmp_path,
        sunshine_api_url="https://localhost:47990",
        sunshine_api_username="admin",
        sunshine_api_password="secret",
        sunshine_verify_tls=False,
    )

    assert result.status == "succeeded"

    contents = state_file.read_text()

    assert "1234" not in contents
    assert "secret" not in contents
    assert "CLIENT-1" in contents


def test_stop_revokes_all_runtime_clients(
    tmp_path,
    monkeypatch,
):
    session_id = uuid4()
    runtime_id = f"kc-gaming-{session_id}"

    state_file = (
        tmp_path
        / "sessions"
        / f"{runtime_id}.json"
    )
    state_file.parent.mkdir(parents=True)

    state_file.write_text(
        """{
  "session_id": "%s",
  "runtime_id": "%s",
  "status": "running",
  "gpu_uuid": "GPU-A",
  "minimum_vram_mb": 8192,
  "paired_clients": [
    {
      "sunshine_client_uuid": "CLIENT-1",
      "client_name": "KC-CLIENT"
    }
  ]
}
""" % (session_id, runtime_id)
    )

    monkeypatch.setattr(
        gaming_runtime,
        "_validate_windows_native",
        lambda **kwargs: {},
    )

    revoked = []

    monkeypatch.setattr(
        gaming_runtime,
        "unpair_client",
        lambda **kwargs: (
            revoked.append(
                kwargs["client_uuid"]
            )
            or {
                "sunshine_client_uuid":
                    kwargs["client_uuid"],
                "revoked": True,
            }
        ),
    )

    result = gaming_runtime.change_session_state(
        {"session_id": str(session_id)},
        state_root=tmp_path,
        execution_backend="windows_native",
        streaming_backend="sunshine",
        action="stop",
        sunshine_api_username="admin",
        sunshine_api_password="secret",
    )

    assert result.status == "succeeded"
    assert revoked == ["CLIENT-1"]

    contents = state_file.read_text()

    assert '"paired_clients": []' in contents
    assert '"status": "stopped"' in contents


def test_connection_pairing_respects_gaming_execution_policy(
    tmp_path,
):
    from khan_agent.job_dispatch import execute_node_job

    result = execute_node_job(
        {
            "job_type": "gaming.connection.pair",
            "payload": {
                "session_id": str(uuid4()),
                "lease_id": str(uuid4()),
                "pin": "1234",
                "client_name": "KC-CLIENT",
            },
        },
        virtualization_execution_enabled=False,
        virtualization_storage_root=Path("/tmp/kc-vps"),
        virtualization_base_image_path=Path(
            "/tmp/base.qcow2"
        ),
        virtualization_network_name="kc-test",
        gaming_execution_enabled=False,
        gaming_execution_backend="windows_native",
        gaming_streaming_backend="sunshine",
        gaming_state_root=tmp_path,
    )

    assert result.status == "blocked"
    assert "disabled by node policy" in result.error_message


def test_connection_revocation_respects_gaming_execution_policy(
    tmp_path,
):
    from khan_agent.job_dispatch import execute_node_job

    result = execute_node_job(
        {
            "job_type": "gaming.connection.revoke",
            "payload": {
                "session_id": str(uuid4()),
                "lease_id": str(uuid4()),
                "sunshine_client_uuid": "CLIENT-1",
            },
        },
        virtualization_execution_enabled=False,
        virtualization_storage_root=Path("/tmp/kc-vps"),
        virtualization_base_image_path=Path(
            "/tmp/base.qcow2"
        ),
        virtualization_network_name="kc-test",
        gaming_execution_enabled=False,
        gaming_execution_backend="windows_native",
        gaming_streaming_backend="sunshine",
        gaming_state_root=tmp_path,
    )

    assert result.status == "blocked"
    assert "disabled by node policy" in result.error_message
