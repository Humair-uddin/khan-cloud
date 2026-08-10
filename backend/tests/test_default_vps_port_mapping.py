from types import SimpleNamespace
from uuid import uuid4

from app.services import gateway_service


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeDB:
    def __init__(self, scalar_results=None):
        self.scalar_results = list(scalar_results or [])
        self.added = []
        self.commits = 0

    def scalar(self, statement):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def scalars(self, statement):
        return FakeScalars([])

    def begin_nested(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def add(self, value):
        self.added.append(value)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def refresh(self, value):
        return None


def gateway():
    return SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )


def vps():
    return SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        status="running",
        primary_ip="10.10.20.150",
    )


def test_default_mapping_is_idempotent():
    existing = SimpleNamespace(
        id=uuid4(),
        protocol="tcp",
        private_port=22,
    )

    db = FakeDB([existing])

    result = gateway_service.ensure_default_vps_port_mapping(
        db,
        gateway=gateway(),
        vps=vps(),
    )

    assert result is existing
    assert db.added == []
    assert db.commits == 0


def test_default_mapping_allocates_ssh_endpoint(monkeypatch):
    db = FakeDB([None])
    test_gateway = gateway()
    test_vps = vps()
    events = []

    monkeypatch.setattr(
        gateway_service,
        "_next_available_port",
        lambda db, gateway_id, protocol: 20042,
    )

    monkeypatch.setattr(
        gateway_service,
        "record_audit_event",
        lambda db, **kwargs: events.append(kwargs),
    )

    result = gateway_service.ensure_default_vps_port_mapping(
        db,
        gateway=test_gateway,
        vps=test_vps,
    )

    assert result.gateway_id == test_gateway.id
    assert result.vps_instance_id == test_vps.id
    assert result.protocol == "tcp"
    assert result.public_port == 20042
    assert result.private_ip == "10.10.20.150"
    assert result.private_port == 22
    assert result.status == "pending"
    assert result.reconcile_action == "apply"
    assert result.allocation_source == "system_provisioning"

    assert len(events) == 1
    assert events[0]["actor_user_id"] is None
    assert events[0]["action"] == "network.port_mapping.allocated"
    assert events[0]["details"]["allocation_source"] == "system_provisioning"

    # Transaction belongs to the provisioning caller.
    assert db.commits == 0


def test_automatic_gateway_selection_requires_one_active_gateway(
    monkeypatch,
):
    test_gateway = gateway()

    monkeypatch.setattr(
        gateway_service,
        "list_public_gateways",
        lambda db, active_only=True: [test_gateway],
    )

    result = gateway_service.select_automatic_public_gateway(
        object()
    )

    assert result is test_gateway


def test_automatic_gateway_selection_rejects_no_gateway(
    monkeypatch,
):
    monkeypatch.setattr(
        gateway_service,
        "list_public_gateways",
        lambda db, active_only=True: [],
    )

    import pytest

    with pytest.raises(
        gateway_service.GatewayError,
        match="No active public gateway",
    ):
        gateway_service.select_automatic_public_gateway(
            object()
        )


def test_automatic_gateway_selection_rejects_ambiguity(
    monkeypatch,
):
    monkeypatch.setattr(
        gateway_service,
        "list_public_gateways",
        lambda db, active_only=True: [
            gateway(),
            gateway(),
        ],
    )

    import pytest

    with pytest.raises(
        gateway_service.GatewayError,
        match="exactly one active public gateway",
    ):
        gateway_service.select_automatic_public_gateway(
            object()
        )
