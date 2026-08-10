from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.services import gateway_reconciliation_worker as worker


class FakeMapping:
    def __init__(self):
        self.id = uuid4()


def test_worker_refuses_to_run_when_live_disabled(monkeypatch):
    monkeypatch.setattr(
        worker.settings,
        "MIKROTIK_LIVE_ENABLED",
        False,
    )

    with pytest.raises(
        worker.GatewayOrchestrationError,
        match="live reconciliation is disabled",
    ):
        worker.reconcile_gateway_batch(
            object(),
            limit=10,
        )


def test_worker_limit_must_be_positive(monkeypatch):
    monkeypatch.setattr(
        worker.settings,
        "MIKROTIK_LIVE_ENABLED",
        True,
    )

    with pytest.raises(
        ValueError,
        match="limit must be at least 1",
    ):
        worker.reconcile_gateway_batch(
            object(),
            limit=0,
        )


def test_worker_processes_one_claim_at_a_time(monkeypatch):
    first = FakeMapping()
    second = FakeMapping()

    queue = [
        first,
        second,
        None,
    ]

    monkeypatch.setattr(
        worker.settings,
        "MIKROTIK_LIVE_ENABLED",
        True,
    )

    claims = []

    def fake_claim(db):
        item = queue.pop(0)
        claims.append(item)
        return item

    monkeypatch.setattr(
        worker,
        "claim_next_reconciliation_candidate",
        fake_claim,
    )

    reconciled = []

    def fake_reconcile(
        db,
        *,
        mapping,
        actor_user_id=None,
    ):
        reconciled.append(mapping.id)
        return mapping

    monkeypatch.setattr(
        worker,
        "reconcile_port_mapping_now",
        fake_reconcile,
    )

    result = worker.reconcile_gateway_batch(
        object(),
        limit=10,
    )

    assert result.selected == 2
    assert result.succeeded == 2
    assert result.failed == 0
    assert result.mapping_ids == (
        first.id,
        second.id,
    )

    assert reconciled == [
        first.id,
        second.id,
    ]

    assert claims == [
        first,
        second,
        None,
    ]


def test_worker_isolates_failure_and_claims_next(monkeypatch):
    first = FakeMapping()
    second = FakeMapping()
    third = FakeMapping()

    queue = [
        first,
        second,
        third,
        None,
    ]

    monkeypatch.setattr(
        worker.settings,
        "MIKROTIK_LIVE_ENABLED",
        True,
    )

    monkeypatch.setattr(
        worker,
        "claim_next_reconciliation_candidate",
        lambda db: queue.pop(0),
    )

    reconciled = []

    def fake_reconcile(
        db,
        *,
        mapping,
        actor_user_id=None,
    ):
        reconciled.append(mapping.id)

        if mapping.id == second.id:
            raise worker.GatewayOrchestrationError(
                "forced failure"
            )

        return mapping

    monkeypatch.setattr(
        worker,
        "reconcile_port_mapping_now",
        fake_reconcile,
    )

    result = worker.reconcile_gateway_batch(
        object(),
        limit=10,
    )

    assert result.selected == 3
    assert result.succeeded == 2
    assert result.failed == 1

    assert reconciled == [
        first.id,
        second.id,
        third.id,
    ]


def test_batch_limit_is_respected(monkeypatch):
    mappings = [
        FakeMapping(),
        FakeMapping(),
        FakeMapping(),
    ]

    queue = list(mappings)

    monkeypatch.setattr(
        worker.settings,
        "MIKROTIK_LIVE_ENABLED",
        True,
    )

    monkeypatch.setattr(
        worker,
        "claim_next_reconciliation_candidate",
        lambda db: queue.pop(0),
    )

    monkeypatch.setattr(
        worker,
        "reconcile_port_mapping_now",
        lambda db, mapping, actor_user_id=None: mapping,
    )

    result = worker.reconcile_gateway_batch(
        object(),
        limit=2,
    )

    assert result.selected == 2
    assert result.mapping_ids == (
        mappings[0].id,
        mappings[1].id,
    )

    assert len(queue) == 1


def test_candidate_claim_uses_skip_locked():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "services"
        / "gateway_reconciliation_worker.py"
    ).read_text()

    assert ".with_for_update(skip_locked=True)" in source
    assert ".limit(1)" in source
