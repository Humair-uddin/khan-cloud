from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _read(path: str) -> str:
    return (ROOT / path).read_text()

def test_operator_recovery_requires_node_maintenance_permission():
    api = _read("app/api/v1/compute.py")
    assert '"/gaming/sessions/{session_id}/quarantine-recovery"' in api
    assert 'require_permission("nodes.maintenance")' in api
    assert 'source="operator"' in api

def test_recovery_reuses_existing_delete_job_and_holds_reservation():
    service = _read("app/services/gaming_service.py")
    assert "def queue_gaming_quarantine_recovery" in service
    assert 'job_type="gaming.session.delete"' in service
    assert '"quarantine_recovery": True' in service
    assert "release_gaming_reservation" not in service.split(
        "def queue_gaming_quarantine_recovery", 1
    )[1].split("def reconcile_quarantined_gaming_sessions_for_node", 1)[0]

def test_automatic_recovery_is_bounded_and_heartbeat_driven():
    service = _read("app/services/gaming_service.py")
    nodes = _read("app/api/v1/nodes.py")
    assert "GAMING_QUARANTINE_AUTO_RECOVERY_MAX_ATTEMPTS = 3" in service
    assert "GAMING_QUARANTINE_AUTO_RECOVERY_COOLDOWN_SECONDS = 60" in service
    assert "def reconcile_quarantined_gaming_sessions_for_node" in service
    assert "reconcile_quarantined_gaming_sessions_for_node" in nodes
    assert 'source="automatic"' in service

def test_repool_requires_both_sanitization_and_fresh_host_revalidation():
    service = _read("app/services/gaming_service.py")
    assert "proof_ok" in service
    assert "host_revalidated" in service
    assert "gaming_host_readiness_reasons(node, now=now)" in service
    assert "post_sanitization_host_revalidation_failed" in service
    assert "runtime_host_revalidation_failed" in service

def test_delete_failure_is_quarantined_not_generic_error():
    service = _read("app/services/gaming_service.py")
    assert 'session.quarantine_reason = "gaming_session_delete_failed"' in service
    assert 'session.failure_category = "runtime_sanitization_failed"' in service

def test_recovery_audit_fields_are_persisted():
    model = _read("app/models/compute.py")
    for name in (
        "quarantine_recovery_state",
        "quarantine_recovery_attempt_count",
        "quarantine_recovery_requested_at",
        "quarantine_recovery_last_attempt_at",
        "quarantine_recovery_last_source",
        "quarantine_recovery_last_message",
        "quarantine_recovery_last_evidence",
        "quarantine_recovered_at",
    ):
        assert name in model

def test_c6_migration_follows_c5():
    migration = _read(
        "migrations/versions/c6a009f10001_gaming_quarantine_recovery_v1.py"
    )
    assert 'revision = "c6a009f10001"' in migration
    assert 'down_revision = "c5a009f10001"' in migration
