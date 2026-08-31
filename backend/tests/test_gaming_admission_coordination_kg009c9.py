from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def r(path): return (ROOT / path).read_text()

def test_drain_serializes_on_same_node_capacity_lock_as_scheduler():
    s=r("app/services/gaming_service.py")
    scheduler=s.split("def select_gaming_host",1)[1].split("def ",1)[0]
    drain=s.split("def request_gaming_node_drain",1)[1].split("def reconcile_gaming_node_drain",1)[0]
    assert ".with_for_update(of=NodeCapacity)" in scheduler
    assert "select(NodeCapacity)" in drain
    assert ".with_for_update()" in drain
    assert drain.index(".with_for_update()") < drain.index("transition_node(")

def test_direct_maintenance_with_live_gaming_ownership_is_blocked():
    s=r("app/services/node_service.py")
    x=s.split("def transition_node",1)[1]
    assert 'current == "approved" and new_state == "maintenance"' in x
    assert "gaming_node_active_reservation_count" in x
    assert "gaming_node_inflight_job_count" in x
    assert "use controlled drain before maintenance" in x

def test_recovery_readiness_is_separate_from_placement_readiness():
    s=r("app/services/gaming_service.py")
    x=s.split("def gaming_recovery_readiness_reasons",1)[1].split("def gaming_maintenance_reentry_reasons",1)[0]
    assert '{"approved", "draining", "maintenance"}' in x
    assert "gaming_accepting_work" not in x
    assert "gaming_host_is_ready" not in x

def test_automatic_quarantine_recovery_uses_recovery_gate():
    s=r("app/services/gaming_service.py")
    x=s.split("def reconcile_quarantined_gaming_sessions_for_node",1)[1].split("def reconcile_gaming_runtime_health_for_node",1)[0]
    assert "gaming_recovery_readiness_reasons(node, now=now)" in x
    assert "gaming_host_is_ready(node)" not in x

def test_delete_revalidation_preserves_c6_and_allows_c9_cleanup_gate():
    s=r("app/services/gaming_service.py")
    x=s.split('elif job.job_type == "gaming.session.delete":',1)[1]

    # Frozen C6 behavior remains authoritative for approved/schedulable hosts.
    assert 'node.lifecycle_state == "approved"' in x
    assert "gaming_host_readiness_reasons(node, now=now)" in x

    # C9 permits cleanup proof while draining/maintenance without granting
    # scheduler admission. Formatting of the function call is intentionally
    # irrelevant to this source-contract test.
    assert "gaming_recovery_readiness_reasons(" in x
    assert "node," in x
    assert "now=now," in x

    # Sanitization/revalidation is still followed by the existing reservation
    # release path rather than a direct lifecycle/admission mutation.
    assert "release_gaming_reservation(db, session)" in x

def test_maintenance_reentry_requires_c8_health_and_capacity_execution():
    s=r("app/services/gaming_service.py")
    x=s.split("def gaming_maintenance_reentry_reasons",1)[1].split("def request_gaming_node_drain",1)[0]
    assert 'node.gaming_health_state != "healthy"' in x
    assert "capacity_execution_disabled" in x
    assert "capacity_scheduling_disabled" in x
    assert "node_capacity_missing" in x

def test_recovery_does_not_mutate_lifecycle_or_admission():
    s=r("app/services/gaming_service.py")
    x=s.split("def gaming_recovery_readiness_reasons",1)[1].split("def gaming_maintenance_reentry_reasons",1)[0]
    assert "node.lifecycle_state =" not in x
    assert "node.gaming_accepting_work =" not in x

def test_no_new_c9_database_or_parallel_health_state():
    assert not (ROOT/"migrations/versions/c9a009f10001").exists()
    s=r("app/services/node_service.py")
    states=s.split("LIFECYCLE_STATES",1)[1].split("}",1)[0]
    assert '"degraded"' not in states
