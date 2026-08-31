from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _read(path: str) -> str:
    return (ROOT / path).read_text()

def test_draining_evolves_existing_node_lifecycle():
    service = _read("app/services/node_service.py")
    assert '"draining"' in service
    assert '"approved": {"draining","maintenance","disabled","retired"}' in service
    assert '"draining": {"maintenance","disabled","retired"}' in service

def test_drain_uses_existing_maintenance_permission_and_blocks_new_work():
    api = _read("app/api/v1/nodes.py")
    service = _read("app/services/node_service.py")
    assert '"/{node_id}/drain"' in api
    drain_section = api.split('"/{node_id}/drain"', 1)[1].split('@router.post("/{node_id}/maintenance"', 1)[0]
    assert 'require_permission("nodes.maintenance")' in drain_section
    assert 'new_state="draining"' in _read("app/services/gaming_service.py")
    assert 'node.gaming_accepting_work=False' in service

def test_drain_keeps_heartbeat_allowed():
    service = _read("app/services/node_service.py")
    heartbeat = service.split("def heartbeat_node", 1)[1].split("def transition_node", 1)[0]
    assert '"draining"' not in heartbeat.split("if node.lifecycle_state in", 1)[1].split(":", 1)[0]

def test_graceful_drain_preserves_existing_sessions():
    service = _read("app/services/gaming_service.py")
    section = service.split("def request_gaming_node_drain", 1)[1].split("def reconcile_gaming_node_drain", 1)[0]
    assert "terminate_active_sessions" in section
    assert "if terminate_active_sessions:" in section
    assert 'action="terminate"' in section

def test_drain_completion_requires_zero_reservations_and_jobs():
    service = _read("app/services/gaming_service.py")
    section = service.split("def reconcile_gaming_node_drain", 1)[1].split("def queue_gaming_quarantine_recovery", 1)[0]
    assert "gaming_node_active_reservation_count" in section
    assert "gaming_node_inflight_job_count" in section
    assert 'node.lifecycle_state = "maintenance"' in section

def test_maintenance_reentry_is_fail_closed_for_gaming_hosts():
    node_service = _read("app/services/node_service.py")
    gaming = _read("app/services/gaming_service.py")
    assert "gaming_maintenance_reentry_reasons" in node_service
    assert 'current == "maintenance" and new_state == "approved"' in node_service
    for gate in (
        "active_gaming_reservations",
        "inflight_gaming_jobs",
        "interactive_session_unavailable",
        "sunshine_unavailable",
        "gpu_unavailable",
    ):
        assert gate in gaming

def test_no_parallel_teardown_or_force_release():
    service = _read("app/services/gaming_service.py")
    drain = service.split("def request_gaming_node_drain", 1)[1].split("def reconcile_gaming_node_drain", 1)[0]
    assert "queue_gaming_action" in drain
    assert "release_gaming_reservation" not in drain
    assert "gaming.session.delete" not in drain

def test_scheduler_already_excludes_draining():
    service = _read("app/services/gaming_service.py")
    select_host = service.split("def select_gaming_host", 1)[1].split("def ", 1)[0]
    assert '.where(Node.lifecycle_state == "approved")' in select_host
    assert '.where(Node.gaming_accepting_work.is_(True))' in select_host
