from __future__ import annotations

import pytest

from khan_agent import gaming_runtime
from khan_agent import sunshine_broker


def test_d3_stream_readiness_requires_healthy_vdd(monkeypatch):
    monkeypatch.setattr(
        gaming_runtime,
        "probe_sunshine_readiness",
        lambda **kwargs: {"ready": True},
    )

    with pytest.raises(
        gaming_runtime.GamingRuntimeError,
        match="healthy post-activation",
    ):
        gaming_runtime._verify_stream_readiness(
            runtime_id="kc-gaming-test",
            runtime_ownership={
                "ownership_type": "none",
            },
            launch_info=None,
            display_activation={"healthy": False},
            sunshine_api_url="https://127.0.0.1:47990",
            sunshine_api_username="admin",
            sunshine_api_password="secret",
            sunshine_verify_tls=False,
        )


def test_d3_stream_readiness_requires_sunshine_api(monkeypatch):
    monkeypatch.setattr(
        gaming_runtime,
        "probe_sunshine_readiness",
        lambda **kwargs: (_ for _ in ()).throw(
            sunshine_broker.SunshineBrokerError(
                "Sunshine authenticated API is not reachable."
            )
        ),
    )

    with pytest.raises(
        gaming_runtime.GamingRuntimeError,
        match=(
            "Sunshine stream readiness could not be verified: "
            "Sunshine authenticated API is not reachable"
        ),
    ):
        gaming_runtime._verify_stream_readiness(
            runtime_id="kc-gaming-test",
            runtime_ownership={
                "ownership_type": "none",
            },
            launch_info=None,
            display_activation=None,
            sunshine_api_url="https://127.0.0.1:47990",
            sunshine_api_username="admin",
            sunshine_api_password="secret",
            sunshine_verify_tls=False,
        )


def test_d3_game_requires_owned_process(monkeypatch):
    monkeypatch.setattr(
        gaming_runtime,
        "probe_sunshine_readiness",
        lambda **kwargs: {"ready": True},
    )
    monkeypatch.setattr(
        gaming_runtime,
        "inspect_runtime_ownership",
        lambda ownership: {
            "ownership_boundary_verified": True,
            "owned_process_count": 0,
        },
    )

    with pytest.raises(
        gaming_runtime.GamingRuntimeError,
        match="no live process",
    ):
        gaming_runtime._verify_stream_readiness(
            runtime_id="kc-gaming-test",
            runtime_ownership={
                "ownership_type": "windows_job_object",
            },
            launch_info={"launcher_pid": 4242},
            display_activation=None,
            sunshine_api_url="https://127.0.0.1:47990",
            sunshine_api_username="admin",
            sunshine_api_password="secret",
            sunshine_verify_tls=False,
        )


def test_d3_generic_runtime_allows_no_process(monkeypatch):
    monkeypatch.setattr(
        gaming_runtime,
        "probe_sunshine_readiness",
        lambda **kwargs: {
            "ready": True,
            "authenticated_api": True,
        },
    )
    monkeypatch.setattr(
        gaming_runtime,
        "inspect_runtime_ownership",
        lambda ownership: {
            "ownership_boundary_verified": True,
            "owned_process_count": 0,
        },
    )

    proof = gaming_runtime._verify_stream_readiness(
        runtime_id="kc-gaming-test",
        runtime_ownership={
            "ownership_type": "none",
        },
        launch_info=None,
        display_activation=None,
        sunshine_api_url="https://127.0.0.1:47990",
        sunshine_api_username="admin",
        sunshine_api_password="secret",
        sunshine_verify_tls=False,
    )

    assert proof["verified"] is True
    assert proof["workload_process_required"] is False
    assert proof["sunshine"]["ready"] is True


class _Response:
    status_code = 200
    is_error = False

    def json(self):
        return {"clients": []}


class _Client:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, path):
        assert path == "/api/clients/list"
        return _Response()


def test_d3_sunshine_probe_uses_authenticated_api(monkeypatch):
    monkeypatch.setattr(
        sunshine_broker.httpx,
        "Client",
        _Client,
    )

    result = sunshine_broker.probe_sunshine_readiness(
        api_url="https://127.0.0.1:47990",
        username="admin",
        password="secret",
        verify_tls=False,
    )

    assert result == {
        "ready": True,
        "authenticated_api": True,
        "endpoint": "/api/clients/list",
    }
