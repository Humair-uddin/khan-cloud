from pathlib import Path

from pydantic import ValidationError
import pytest

from app.schemas.compute import GamingConnectionLeaseCreate, GamingConnectionLeaseEventRequest
from app.services.gaming_connection_service import _token_hash


def test_c4_connection_policy_is_bounded():
    policy = GamingConnectionLeaseCreate()
    assert policy.connection_ttl_seconds == 14400
    assert policy.reconnect_grace_seconds == 120
    with pytest.raises(ValidationError):
        GamingConnectionLeaseCreate(connection_ttl_seconds=60)
    with pytest.raises(ValidationError):
        GamingConnectionLeaseCreate(reconnect_grace_seconds=5)


def test_c4_event_contract_requires_long_token():
    req = GamingConnectionLeaseEventRequest(event="connected", connection_token="x" * 32)
    assert req.event == "connected"
    with pytest.raises(ValidationError):
        GamingConnectionLeaseEventRequest(event="connected", connection_token="short")


def test_c4_hashes_control_plane_token():
    token = "secret-token-that-must-never-be-persisted"
    digest = _token_hash(token)
    assert token not in digest
    assert len(digest) == 64


def test_c4_reuses_existing_connection_broker_and_secure_stop_path():
    root = Path(__file__).resolve().parents[1]
    service = (root / "app/services/gaming_connection_service.py").read_text()
    api = (root / "app/api/v1/compute.py").read_text()
    nodes = (root / "app/api/v1/nodes.py").read_text()
    assert '"gaming.connection.pair"' in service
    assert '"gaming.connection.revoke"' in service
    assert "hmac.compare_digest" in service
    assert "reconnect_grace" in service
    assert "queue_gaming_action" in service
    assert "connection_token" in api
    assert "reconcile_connection_leases_for_node" in nodes


def test_c4_never_exposes_token_hash_in_read_schema():
    root = Path(__file__).resolve().parents[1]
    schema = (root / "app/schemas/compute.py").read_text()
    read = schema[schema.index("class GamingConnectionLeaseRead"):schema.index("class GamingConnectionLeaseIssue")]
    assert "connection_token_hash" not in read
