from pathlib import Path
from types import SimpleNamespace

from app.schemas.compute import GamingSessionCreate
from app.services.gaming_service import _gpu_fields, _gpu_inventory


def test_gaming_session_has_production_8gb_floor():
    payload = GamingSessionCreate(name="premium-game")
    assert payload.minimum_vram_mb == 8192


def test_gaming_session_rejects_below_8gb_floor():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        GamingSessionCreate(name="low-vram", minimum_vram_mb=4096)


def test_gpu_inventory_reads_agent_inventory_contract():
    node = SimpleNamespace(inventory={"gpu": {"gpus": [{"uuid": "GPU-1", "name": "RTX 3080", "memory_total_mib": 10240}]}})
    devices = _gpu_inventory(node)
    assert _gpu_fields(devices[0]) == ("GPU-1", "RTX 3080", 10240)


def test_gaming_api_and_rbac_are_wired():
    root = Path(__file__).resolve().parents[1]
    api = (root / "app/api/v1/compute.py").read_text()
    rbac = (root / "app/services/rbac_service.py").read_text()
    assert '"/gaming/sessions"' in api
    assert '"/gaming/sessions/{session_id}/actions"' in api
    assert 'require_permission("gaming.read")' in api
    assert 'require_permission("gaming.manage")' in api
    assert '"gaming.read"' in rbac and '"gaming.manage"' in rbac


def test_gaming_jobs_share_authoritative_node_job_channel():
    root = Path(__file__).resolve().parents[1]
    model = (root / "app/models/compute.py").read_text()
    service = (root / "app/services/gaming_service.py").read_text()
    compute = (root / "app/services/compute_service.py").read_text()
    assert "gaming_session_id" in model
    assert 'job_type="gaming.session.create"' in service
    assert "finish_gaming_job" in compute


def test_scheduler_uses_capability_not_gpu_model_allowlist():
    root = Path(__file__).resolve().parents[1]
    service = (root / "app/services/gaming_service.py").read_text().lower()
    assert "minimum_vram_mb" in service
    assert "approved_models" not in service
    assert "allowlist" not in service


def test_lifecycle_has_reservation_release_and_inflight_guard():
    root = Path(__file__).resolve().parents[1]
    service = (root / "app/services/gaming_service.py").read_text()
    assert "release_gaming_reservation" in service
    assert "in-flight operation" in service
    assert 'session.status = "terminated"' in service

def test_gaming_lifecycle_uses_canonical_stopped_state():
    from pathlib import Path

    service = Path(
        "app/services/gaming_service.py"
    ).read_text()

    assert '"stoped"' not in service
    assert "'stoped'" not in service
    assert '"stopped"' in service


def test_gaming_lifecycle_state_vocabulary_is_consistent():
    from pathlib import Path

    service = Path(
        "app/services/gaming_service.py"
    ).read_text()

    # Start remains an immediate lifecycle transition.
    assert 'session.desired_state = "running"' in service
    assert 'session.status = "starting"' in service
    assert '_gaming_runtime_job_type(session, "start")' in service
    assert '"gaming.session.start"' in service
    assert '"gaming.vm.start"' in service

    # Stop and terminate retain the canonical vocabulary while
    # KG-004B may defer runtime shutdown until connection
    # authorization has been revoked.
    assert '"stopped"' in service
    assert '"terminated"' in service
    assert '"stopping"' in service
    assert '"terminating"' in service

    # Failure remains a canonical lifecycle outcome.
    assert '"failed"' in service
    assert 'session.status = "error"' in service
