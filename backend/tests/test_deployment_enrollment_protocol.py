from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.node import NodeRegistrationResponse
from app.services.deployment_profile_service import DeploymentProfileError, consume_profile_code


class FakeDB:
    def __init__(self):
        self.flushed = 0
        self.committed = 0

    def flush(self):
        self.flushed += 1

    def commit(self):
        self.committed += 1


def test_registration_response_carries_deployment_identity() -> None:
    profile_id = uuid4()
    response = NodeRegistrationResponse(
        node_id=uuid4(),
        node_secret="secret",
        status="pending_approval",
        lifecycle_state="pending_approval",
        deployment_profile_id=profile_id,
        intended_purpose="gpu_compute",
    )
    assert response.deployment_profile_id == profile_id
    assert response.intended_purpose == "gpu_compute"


def test_profile_code_consumption_can_join_outer_transaction() -> None:
    db = FakeDB()
    profile = SimpleNamespace(
        is_active=True,
        expires_at=None,
        uses_count=0,
        max_uses=2,
    )
    consume_profile_code(db, profile, commit=False)
    assert profile.uses_count == 1
    assert db.flushed == 1
    assert db.committed == 0


def test_exhausted_profile_code_is_rejected_before_increment() -> None:
    db = FakeDB()
    profile = SimpleNamespace(
        is_active=True,
        expires_at=None,
        uses_count=1,
        max_uses=1,
    )
    with pytest.raises(DeploymentProfileError, match="no remaining uses"):
        consume_profile_code(db, profile, commit=False)
    assert profile.uses_count == 1
