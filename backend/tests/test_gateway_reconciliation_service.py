from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.gateway.base import GatewayApplyResult
from app.services import gateway_reconciliation_service as service


class FakeDB:
    def __init__(self):
        self.commits = 0
        self.refreshes = 0

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        self.refreshes += 1


class SuccessfulAdapter:
    def ensure_port_mapping(self, rule):
        return GatewayApplyResult(
            changed=True,
            external_id="*KC1",
            message="created",
        )

    def remove_port_mapping(self, rule):
        return GatewayApplyResult(
            changed=True,
            external_id="*KC1",
            message="removed",
        )


class FailingAdapter:
    def ensure_port_mapping(self, rule):
        raise RuntimeError("router unavailable")

    def remove_port_mapping(self, rule):
        raise RuntimeError("router unavailable")


def mapping(*, action="apply", status="pending"):
    return SimpleNamespace(
        id=uuid4(),
        gateway_id=uuid4(),
        vps_instance_id=uuid4(),
        organization_id=uuid4(),
        protocol="tcp",
        public_port=22001,
        private_ip="10.10.10.50",
        private_port=22,
        status=status,
        reconcile_action=action,
        reconcile_error=None,
        reconciled_at=None,
        released_at=None,
        external_id=None,
    )


def gateway():
    return SimpleNamespace(
        id=uuid4(),
        public_ip="203.0.113.10",
        ingress_mode="direct",
        wan_interface=None,
    )


def disable_real_audit(monkeypatch):
    events = []

    def fake_record(*args, **kwargs):
        events.append(kwargs)
        return None

    monkeypatch.setattr(
        service,
        "record_audit_event",
        fake_record,
    )

    return events


def test_apply_success_transitions_mapping_to_active(monkeypatch):
    events = disable_real_audit(monkeypatch)
    db = FakeDB()
    item = mapping(action="apply")

    result = service.reconcile_port_mapping(
        db,
        mapping=item,
        gateway=gateway(),
        adapter=SuccessfulAdapter(),
    )

    assert result.status == "active"
    assert result.external_id == "*KC1"
    assert result.reconcile_error is None
    assert result.reconciled_at is not None
    assert result.released_at is None
    assert db.commits == 1
    assert db.refreshes == 1
    assert events[-1]["action"] == "network.port_mapping.reconciled"


def test_apply_failure_preserves_port_and_retry_intent(monkeypatch):
    events = disable_real_audit(monkeypatch)
    db = FakeDB()
    item = mapping(action="apply")

    with pytest.raises(
        service.GatewayReconciliationError,
        match="router unavailable",
    ):
        service.reconcile_port_mapping(
            db,
            mapping=item,
            gateway=gateway(),
            adapter=FailingAdapter(),
        )

    assert item.status == "failed"
    assert item.reconcile_action == "apply"
    assert item.reconcile_error == "router unavailable"
    assert item.released_at is None
    assert db.commits == 1
    assert events[-1]["result"] == "failed"


def test_failed_apply_can_be_retried(monkeypatch):
    disable_real_audit(monkeypatch)
    db = FakeDB()
    item = mapping(
        action="apply",
        status="failed",
    )
    item.reconcile_error = "previous failure"

    result = service.reconcile_port_mapping(
        db,
        mapping=item,
        gateway=gateway(),
        adapter=SuccessfulAdapter(),
    )

    assert result.status == "active"
    assert result.reconcile_action == "apply"
    assert result.reconcile_error is None
    assert result.external_id == "*KC1"


def test_remove_success_releases_mapping(monkeypatch):
    disable_real_audit(monkeypatch)
    db = FakeDB()
    item = mapping(
        action="remove",
        status="releasing",
    )
    item.external_id = "*KC1"

    result = service.reconcile_port_mapping(
        db,
        mapping=item,
        gateway=gateway(),
        adapter=SuccessfulAdapter(),
    )

    assert result.status == "released"
    assert result.released_at is not None
    assert result.reconciled_at is not None
    assert result.external_id is None


def test_remove_failure_preserves_removal_intent(monkeypatch):
    disable_real_audit(monkeypatch)
    db = FakeDB()
    item = mapping(
        action="remove",
        status="releasing",
    )
    item.external_id = "*KC1"

    with pytest.raises(service.GatewayReconciliationError):
        service.reconcile_port_mapping(
            db,
            mapping=item,
            gateway=gateway(),
            adapter=FailingAdapter(),
        )

    assert item.status == "failed"
    assert item.reconcile_action == "remove"
    assert item.external_id == "*KC1"
    assert item.released_at is None


def test_failed_remove_can_be_retried(monkeypatch):
    disable_real_audit(monkeypatch)
    db = FakeDB()
    item = mapping(
        action="remove",
        status="failed",
    )
    item.external_id = "*KC1"
    item.reconcile_error = "previous failure"

    result = service.reconcile_port_mapping(
        db,
        mapping=item,
        gateway=gateway(),
        adapter=SuccessfulAdapter(),
    )

    assert result.status == "released"
    assert result.reconcile_action == "remove"
    assert result.reconcile_error is None
    assert result.external_id is None


def test_invalid_reconciliation_action_is_rejected(monkeypatch):
    disable_real_audit(monkeypatch)
    db = FakeDB()
    item = mapping(action="something-else")

    with pytest.raises(
        service.GatewayReconciliationError,
        match="Unsupported reconciliation action",
    ):
        service.reconcile_port_mapping(
            db,
            mapping=item,
            gateway=gateway(),
            adapter=SuccessfulAdapter(),
        )

    assert db.commits == 0
