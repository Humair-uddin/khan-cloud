from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.services import compute_service, gaming_service


def test_gaming_job_reclaim_contract_is_scoped_to_gaming_only():
    source = Path(compute_service.__file__).read_text()

    assert 'NodeJob.job_type.like("gaming.%")' in source
    assert "GAMING_JOB_RECLAIM_AFTER_SECONDS = 180" in source
    assert 'NodeJob.status == "running"' in source
    assert "NodeJob.claimed_at <= stale_before" in source


def test_stale_reclaim_increments_recovery_counter():
    job = SimpleNamespace(
        node_id=uuid4(),
        status="running",
        job_type="gaming.session.create",
        claimed_at=datetime.now(UTC) - timedelta(minutes=10),
        attempt_count=1,
        gaming_session_id=uuid4(),
    )
    session = SimpleNamespace(runtime_recovery_count=0)

    class FakeDb:
        def __init__(self):
            self.scalar_calls = 0

        def scalar(self, statement):
            self.scalar_calls += 1
            if self.scalar_calls == 1:
                return None
            return job

        def get(self, model, identifier):
            assert identifier == job.gaming_session_id
            return session

        def commit(self):
            pass

        def refresh(self, value):
            pass

    node = SimpleNamespace(id=job.node_id)
    claimed = compute_service.claim_next_job(FakeDb(), node)

    assert claimed is job
    assert claimed.attempt_count == 2
    assert session.runtime_recovery_count == 1
    assert claimed.claimed_at is not None


def test_runtime_watchdog_requires_three_consecutive_failures(monkeypatch):
    session = SimpleNamespace(
        id=uuid4(),
        node_id=uuid4(),
        status="running",
        desired_state="running",
        runtime_health_failure_count=0,
        runtime_health_last_checked_at=None,
        runtime_health_last_failure_at=None,
        failure_category="",
        failure_message="",
    )
    node = SimpleNamespace(id=session.node_id)
    queued = []

    class FakeDb:
        def scalars(self, statement):
            return [session]

        def scalar(self, statement):
            return None

    monkeypatch.setattr(
        gaming_service,
        "gaming_host_readiness_reasons",
        lambda node, now=None: ["sunshine_unavailable"],
    )
    monkeypatch.setattr(
        gaming_service,
        "queue_gaming_action",
        lambda db, session, action, commit=False: queued.append(action),
    )

    db = FakeDb()

    assert gaming_service.reconcile_gaming_runtime_health_for_node(db, node=node) == []
    assert gaming_service.reconcile_gaming_runtime_health_for_node(db, node=node) == []
    stopped = gaming_service.reconcile_gaming_runtime_health_for_node(db, node=node)

    assert stopped == [session.id]
    assert queued == ["stop"]
    assert session.failure_category == "runtime_health_lost"


def test_runtime_watchdog_recovers_after_good_heartbeat(monkeypatch):
    session = SimpleNamespace(
        id=uuid4(),
        node_id=uuid4(),
        status="running",
        desired_state="running",
        runtime_health_failure_count=2,
        runtime_health_last_checked_at=None,
        runtime_health_last_failure_at=datetime.now(UTC),
        failure_category="",
        failure_message="",
    )
    node = SimpleNamespace(id=session.node_id)

    class FakeDb:
        def scalars(self, statement):
            return [session]

    monkeypatch.setattr(
        gaming_service,
        "gaming_host_readiness_reasons",
        lambda node, now=None: [],
    )

    assert gaming_service.reconcile_gaming_runtime_health_for_node(FakeDb(), node=node) == []
    assert session.runtime_health_failure_count == 0
    assert session.runtime_health_last_failure_at is None


def test_nodes_heartbeat_runs_runtime_and_billing_reconciliation():
    source = Path("app/api/v1/nodes.py").read_text()

    runtime_pos = source.index("reconcile_gaming_runtime_health_for_node")
    billing_pos = source.index("reconcile_gaming_billing_for_node")
    commit_pos = source.index("db.commit()", runtime_pos)

    assert runtime_pos < commit_pos
    assert billing_pos < commit_pos


def test_recovery_migration_and_model_contract():
    model = Path("app/models/compute.py").read_text()
    migration = Path(
        "migrations/versions/c3a009f10001_gaming_runtime_recovery_v1.py"
    ).read_text()

    for field in (
        "runtime_health_failure_count",
        "runtime_health_last_checked_at",
        "runtime_health_last_failure_at",
        "runtime_recovery_count",
    ):
        assert field in model
        assert field in migration

    assert 'down_revision = "c2a009f10001"' in migration
