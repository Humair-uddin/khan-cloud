from types import SimpleNamespace
from uuid import uuid4

from app.services import compute_service


class FakeDB:
    def __init__(self, *, job=None):
        self.job = job
        self.commits = 0
        self.refreshes = []

    def scalar(self, statement):
        return self.job

    def get(self, model, object_id):
        if self.job is not None and object_id == self.job.id:
            return self.job
        return None

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        self.refreshes.append(item)


def _job(*, status="pending", gaming=True):
    return SimpleNamespace(
        id=uuid4(),
        node_id=uuid4(),
        vps_instance_id=None,
        gaming_session_id=uuid4() if gaming else None,
        job_type="gaming.session.create" if gaming else "unknown",
        payload={},
        status=status,
        attempt_count=0,
        claimed_at=None,
        completed_at=None,
        result={},
        error_message="",
    )


def test_claim_next_gaming_job_only_claims_and_never_reconciles(monkeypatch):
    job = _job()
    node = SimpleNamespace(id=job.node_id)
    db = FakeDB(job=job)

    # Regression for the pre-V1 bridge bug: claiming a job must not try to
    # finish/reconcile it using result variables that do not exist yet.
    claimed = compute_service.claim_next_job(db, node)

    assert claimed is job
    assert job.status == "running"
    assert job.attempt_count == 1
    assert job.claimed_at is not None
    assert db.commits == 1
    assert db.refreshes == [job]


def test_finish_job_routes_gaming_result_to_gaming_reconciler(monkeypatch):
    job = _job(status="running")
    node = SimpleNamespace(id=job.node_id)
    db = FakeDB(job=job)
    calls = []

    from app.services import gaming_service

    monkeypatch.setattr(
        gaming_service,
        "finish_gaming_job",
        lambda db_arg, **kwargs: calls.append((db_arg, kwargs)),
    )

    result = compute_service.finish_job(
        db,
        node=node,
        job_id=job.id,
        status="succeeded",
        result={"runtime_id": "kc-gaming-test"},
        error_message="",
    )

    assert result is job
    assert job.status == "succeeded"
    assert job.result == {"runtime_id": "kc-gaming-test"}
    assert len(calls) == 1
    assert calls[0][0] is db
    assert calls[0][1]["job"] is job
    assert calls[0][1]["status"] == "succeeded"


def test_duplicate_node_result_is_idempotent(monkeypatch):
    job = _job(status="succeeded")
    node = SimpleNamespace(id=job.node_id)
    db = FakeDB(job=job)

    from app.services import gaming_service

    monkeypatch.setattr(
        gaming_service,
        "finish_gaming_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("terminal job must not reconcile twice")
        ),
    )

    returned = compute_service.finish_job(
        db,
        node=node,
        job_id=job.id,
        status="succeeded",
        result={"runtime_id": "ignored"},
        error_message="",
    )

    assert returned is job
    assert db.commits == 0
