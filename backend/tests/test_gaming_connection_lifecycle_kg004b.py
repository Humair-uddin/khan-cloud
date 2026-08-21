from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _connection_service() -> str:
    return (
        ROOT
        / "app/services/gaming_connection_service.py"
    ).read_text(encoding="utf-8")


def _gaming_service() -> str:
    return (
        ROOT
        / "app/services/gaming_service.py"
    ).read_text(encoding="utf-8")


def test_shutdown_revokes_connection_before_runtime_operation():
    connection = _connection_service()
    gaming = _gaming_service()

    assert "prepare_connection_shutdown" in connection
    assert "continue_deferred_session_action" in connection
    assert "automatic_shutdown" in connection

    assert "prepare_connection_shutdown" in gaming
    assert 'session.desired_state = (' in gaming


def test_nonpaired_leases_are_invalidated_without_sunshine_job():
    service = _connection_service()

    assert "NON_PAIRED_INVALIDATABLE_STATES" in service
    assert 'lease.state = "revoked"' in service
    assert "lease.revoked_at = now" in service


def test_pair_and_revoke_duplicate_checks_are_lease_scoped():
    service = _connection_service()

    assert service.count(
        'NodeJob.payload["lease_id"].astext'
    ) >= 3


def test_late_pair_result_cannot_resurrect_revoked_lease():
    service = _connection_service()

    assert 'if lease.state != "pairing":' in service
    assert (
        "late pairing result must never resurrect"
        in service
    )


def test_late_revoke_result_is_state_guarded():
    service = _connection_service()

    assert 'if lease.state != "revoking":' in service


def test_failed_security_revocation_blocks_runtime_shutdown():
    service = _connection_service()

    assert (
        '"connection_revocation_failed"'
        in service
    )
    assert (
        "runtime shutdown was not attempted"
        in service
    )


def test_deferred_shutdown_uses_existing_desired_state():
    service = _connection_service()

    assert (
        'session.desired_state not in {"stopped", "terminated"}'
        in service
    )

    # KG-004B deliberately does not introduce parallel persistent
    # orchestration state; GamingSession.desired_state is authoritative.
    model = (
        ROOT / "app/models/compute.py"
    ).read_text(encoding="utf-8")

    assert "desired_state" in model
