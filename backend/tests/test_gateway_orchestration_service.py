from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import gateway_orchestration_service as service


class FakeDB:
    def __init__(self, gateway=None):
        self.gateway = gateway

    def get(self, model, identifier):
        return self.gateway


def mapping(
    *,
    status="pending",
    action="apply",
):
    return SimpleNamespace(
        id=uuid4(),
        gateway_id=uuid4(),
        status=status,
        reconcile_action=action,
    )


def gateway():
    return SimpleNamespace(
        id=uuid4(),
        gateway_type="mikrotik",
        is_active=True,
    )


def test_disabled_live_mode_preserves_pending_state(
    monkeypatch,
):
    monkeypatch.setattr(
        service.settings,
        "MIKROTIK_LIVE_ENABLED",
        False,
    )

    item = mapping()

    result = service.reconcile_port_mapping_if_enabled(
        FakeDB(),
        mapping=item,
    )

    assert result is item
    assert result.status == "pending"


def test_disabled_live_mode_does_not_build_adapter(
    monkeypatch,
):
    monkeypatch.setattr(
        service.settings,
        "MIKROTIK_LIVE_ENABLED",
        False,
    )

    monkeypatch.setattr(
        service,
        "build_gateway_adapter",
        lambda gateway: pytest.fail(
            "adapter must not be created"
        ),
    )

    service.reconcile_port_mapping_if_enabled(
        FakeDB(),
        mapping=mapping(),
    )


def test_explicit_reconcile_rejects_when_live_disabled(
    monkeypatch,
):
    monkeypatch.setattr(
        service.settings,
        "MIKROTIK_LIVE_ENABLED",
        False,
    )

    with pytest.raises(
        service.GatewayOrchestrationError,
        match="live reconciliation is disabled",
    ):
        service.reconcile_port_mapping_now(
            FakeDB(),
            mapping=mapping(),
        )


def test_enabled_mode_invokes_reconciliation(
    monkeypatch,
):
    monkeypatch.setattr(
        service.settings,
        "MIKROTIK_LIVE_ENABLED",
        True,
    )

    gw = gateway()
    db = FakeDB(gw)
    item = mapping()

    fake_adapter = SimpleNamespace(
        close=lambda: None,
    )

    monkeypatch.setattr(
        service,
        "build_gateway_adapter",
        lambda gateway: fake_adapter,
    )

    calls = {}

    def fake_reconcile(
        db,
        *,
        mapping,
        gateway,
        adapter,
        actor_user_id=None,
    ):
        calls["mapping"] = mapping
        calls["gateway"] = gateway
        calls["adapter"] = adapter
        mapping.status = "active"
        return mapping

    monkeypatch.setattr(
        service,
        "reconcile_port_mapping",
        fake_reconcile,
    )

    result = service.reconcile_port_mapping_now(
        db,
        mapping=item,
    )

    assert result.status == "active"
    assert calls["mapping"] is item
    assert calls["gateway"] is gw
    assert calls["adapter"] is fake_adapter


def test_released_mapping_is_idempotent(
    monkeypatch,
):
    monkeypatch.setattr(
        service.settings,
        "MIKROTIK_LIVE_ENABLED",
        True,
    )

    item = mapping(
        status="released",
        action="remove",
    )

    assert (
        service.reconcile_port_mapping_now(
            FakeDB(),
            mapping=item,
        )
        is item
    )


def test_inactive_gateway_blocks_new_apply(
    monkeypatch,
):
    monkeypatch.setattr(
        service.settings,
        "MIKROTIK_LIVE_ENABLED",
        True,
    )

    gw = gateway()
    gw.is_active = False

    with pytest.raises(
        service.GatewayOrchestrationError,
        match="not active",
    ):
        service.reconcile_port_mapping_now(
            FakeDB(gw),
            mapping=mapping(
                action="apply",
            ),
        )


def test_inactive_gateway_can_still_remove(
    monkeypatch,
):
    monkeypatch.setattr(
        service.settings,
        "MIKROTIK_LIVE_ENABLED",
        True,
    )

    gw = gateway()
    gw.is_active = False

    fake_adapter = SimpleNamespace(
        close=lambda: None,
    )

    monkeypatch.setattr(
        service,
        "build_gateway_adapter",
        lambda gateway: fake_adapter,
    )

    def fake_reconcile(
        db,
        *,
        mapping,
        gateway,
        adapter,
        actor_user_id=None,
    ):
        mapping.status = "released"
        return mapping

    monkeypatch.setattr(
        service,
        "reconcile_port_mapping",
        fake_reconcile,
    )

    item = mapping(
        status="releasing",
        action="remove",
    )

    result = service.reconcile_port_mapping_now(
        FakeDB(gw),
        mapping=item,
    )

    assert result.status == "released"
