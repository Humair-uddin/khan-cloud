from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.compute import NodeJob
from app.services.compute_service import ComputeError
from app.services.gaming_service import finish_gaming_job, queue_gaming_play


class FakeDb:
    def __init__(self, *, title=None, pending=None, session=None):
        self.title = title
        self.pending = pending
        self.session = session
        self.added = []
        self.commits = 0
        self.flushes = 0

    def get(self, model, identity):
        if model.__name__ == "GamingTitle":
            return self.title
        if model.__name__ == "GamingSession":
            return self.session
        return None

    def scalar(self, statement):
        return self.pending

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def refresh(self, value):
        return None

    def flush(self):
        self.flushes += 1


def title():
    return SimpleNamespace(
        id=uuid4(),
        slug="counter-strike-2",
        launcher="steam",
        launcher_app_id="730",
    )


def session(**overrides):
    values = {
        "id": uuid4(),
        "gaming_title_id": uuid4(),
        "node_id": uuid4(),
        "runtime_id": "kc-gaming-authoritative",
        "status": "running",
        "desired_state": "running",
        "deployment_stage": "stream_ready",
        "deployment_mode": "bare_metal",
        "usage_reservation_id": uuid4(),
        "billing_finalized_at": None,
        "billing_stop_reason": "",
        "connection_info": {"stream": "unchanged"},
        "failure_category": "",
        "failure_message": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def commercial_snapshot(value):
    return {
        key: getattr(value, key)
        for key in (
            "status",
            "desired_state",
            "deployment_stage",
            "usage_reservation_id",
            "billing_finalized_at",
            "billing_stop_reason",
            "connection_info",
        )
    }


def test_ready_session_queues_one_server_authoritative_play_without_mutation():
    item = session()
    assigned = title()
    item.gaming_title_id = assigned.id
    before = commercial_snapshot(item)
    db = FakeDb(title=assigned)

    returned = queue_gaming_play(db, session=item)

    assert returned is item
    assert commercial_snapshot(item) == before
    assert db.commits == 1
    assert len(db.added) == 1
    job = db.added[0]
    assert isinstance(job, NodeJob)
    assert job.job_type == "gaming.workload.play"
    assert job.node_id == item.node_id
    assert job.gaming_session_id == item.id
    assert job.payload == {
        "session_id": str(item.id),
        "runtime_id": item.runtime_id,
        "gaming_title_id": str(assigned.id),
        "game_slug": "counter-strike-2",
        "launcher_type": "steam",
        "launcher_game_id": "730",
    }
    assert not {
        "executable",
        "install_path",
        "gpu_uuid",
    }.intersection(job.payload)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "stopped"}, "must be running"),
        ({"desired_state": "stopped"}, "not desired running"),
        ({"deployment_stage": "presentation_ready"}, "stream-ready"),
        ({"deployment_mode": "proxmox_windows_vm"}, "only for bare_metal"),
        ({"deployment_mode": "unknown"}, "only for bare_metal"),
        ({"node_id": None}, "not assigned to a node"),
        ({"runtime_id": ""}, "no persisted runtime identity"),
        ({"gaming_title_id": None}, "no assigned title"),
    ],
)
def test_play_preconditions_fail_closed(overrides, message):
    item = session(**overrides)
    assigned = title()
    if "gaming_title_id" not in overrides:
        item.gaming_title_id = assigned.id
    db = FakeDb(title=assigned)

    with pytest.raises(ComputeError, match=message):
        queue_gaming_play(db, session=item)

    assert db.added == []


def test_missing_assigned_title_rejects_play():
    item = session()
    with pytest.raises(ComputeError, match="does not exist"):
        queue_gaming_play(FakeDb(title=None), session=item)


@pytest.mark.parametrize("job_type", ["gaming.session.stop", "gaming.workload.play"])
def test_conflicting_or_duplicate_inflight_job_rejects_play(job_type):
    item = session()
    assigned = title()
    item.gaming_title_id = assigned.id
    pending = SimpleNamespace(job_type=job_type, status="pending")
    db = FakeDb(title=assigned, pending=pending)

    with pytest.raises(ComputeError, match="in-flight operation"):
        queue_gaming_play(db, session=item)


@pytest.mark.parametrize("result_status", ["succeeded", "failed", "blocked"])
def test_play_result_processing_never_changes_commercial_or_billing_state(
    result_status,
):
    item = session()
    before = commercial_snapshot(item) | {
        "failure_category": item.failure_category,
        "failure_message": item.failure_message,
    }
    db = FakeDb(session=item)
    job = SimpleNamespace(
        gaming_session_id=item.id,
        job_type="gaming.workload.play",
        payload={"session_id": str(item.id)},
    )

    finish_gaming_job(
        db,
        job=job,
        status=result_status,
        result={"play_state": "dispatched"},
        error_message="launcher rejected",
    )

    after = commercial_snapshot(item) | {
        "failure_category": item.failure_category,
        "failure_message": item.failure_message,
    }
    assert after == before


def test_play_http_handler_accepts_no_customer_launch_payload():
    from inspect import signature
    from app.api.v1.compute import gaming_session_play

    assert set(signature(gaming_session_play).parameters) == {
        "session_id",
        "user",
        "db",
    }
