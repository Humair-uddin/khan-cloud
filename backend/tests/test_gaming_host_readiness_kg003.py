from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.gaming_service import (
    gaming_host_is_ready,
    gaming_host_readiness_reasons,
)


def _node(**overrides):
    values = {
        "lifecycle_state": "approved",
        "is_enabled": True,
        "intended_purpose": "gaming_host",
        "gaming_accepting_work": True,
        "connectivity_state": "online",
        "last_seen_at": datetime.now(UTC),
        "nvidia_available": True,
        "gpu_count": 1,
        "inventory": {
            "gaming": {
                "interactive_session": {
                    "available": True,
                    "session_id": 1,
                    "username": "TEST\\KC-01",
                },
                "streaming": {
                    "sunshine": {
                        "installed": True,
                        "ready": True,
                    }
                },
            }
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_ready_gaming_host():
    node = _node()
    assert gaming_host_readiness_reasons(node) == []
    assert gaming_host_is_ready(node) is True


def test_provider_can_withdraw_gaming_host():
    node = _node(gaming_accepting_work=False)

    assert "gaming_work_disabled" in gaming_host_readiness_reasons(node)
    assert gaming_host_is_ready(node) is False


def test_stale_heartbeat_blocks_gaming():
    node = _node(
        last_seen_at=datetime.now(UTC) - timedelta(minutes=10)
    )

    assert "node_stale" in gaming_host_readiness_reasons(node)
    assert gaming_host_is_ready(node) is False


def test_missing_interactive_session_blocks_gaming():
    node = _node(
        inventory={
            "gaming": {
                "interactive_session": {
                    "available": False,
                    "session_id": None,
                    "username": "",
                },
                "streaming": {
                    "sunshine": {
                        "installed": True,
                        "ready": True,
                    }
                },
            }
        }
    )

    assert (
        "interactive_session_unavailable"
        in gaming_host_readiness_reasons(node)
    )


def test_sunshine_not_ready_blocks_gaming():
    node = _node(
        inventory={
            "gaming": {
                "interactive_session": {
                    "available": True,
                    "session_id": 1,
                    "username": "TEST\\KC-01",
                },
                "streaming": {
                    "sunshine": {
                        "installed": True,
                        "ready": False,
                    }
                },
            }
        }
    )

    assert "sunshine_unavailable" in gaming_host_readiness_reasons(node)
