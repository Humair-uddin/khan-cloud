from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text()


def test_stop_job_persists_reason_and_keeps_legacy_customer_stop_fallback():
    source = _read("app/services/gaming_service.py")
    queue = source.split("def queue_gaming_action(", 1)[1].split(
        "def gaming_node_active_reservation_count", 1
    )[0]
    finish = source.split("def finish_gaming_job(", 1)[1]

    assert "stop_reason: str | None = None" in queue
    assert '"stop_reason"' in queue
    assert 'or "customer_stop"' in queue

    assert '(job.payload or {}).get("stop_reason")' in finish
    assert finish.count('or "customer_stop"') >= 2


def test_runtime_health_stop_has_explicit_provenance():
    source = _read("app/services/gaming_service.py")
    section = source.split(
        "def reconcile_gaming_runtime_health_for_node", 1
    )[1].split("def reconcile_gaming_billing_for_node", 1)[0]

    assert 'stop_reason="runtime_health_lost"' in section


def test_billing_stop_preserves_finance_reason():
    source = _read("app/services/gaming_service.py")
    section = source.split(
        "def reconcile_gaming_billing_for_node", 1
    )[1].split("def finish_gaming_job", 1)[0]

    assert "session.billing_stop_reason" in section
    assert '"billing_reconciliation_failed"' in section
    assert "stop_reason=" in section


def test_connection_stops_carry_customer_and_expiry_provenance():
    source = _read("app/services/gaming_connection_service.py")

    assert 'stop_reason="customer_quit"' in source
    assert "stop_reason=reason" in source
    assert '"connection_token_expired"' in source
    assert '"reconnect_grace_expired"' in source


def test_successful_stop_does_not_unconditionally_finalize_as_customer_stop():
    source = _read("app/services/gaming_service.py")

    assert (
        'finalize_gaming_billing(db, session=session, reason="customer_stop")'
        not in source
    )


def test_deferred_stop_provenance_survives_connection_revocation_source_contract():
    source = _read("app/services/gaming_connection_service.py")

    prepare = source.split(
        "def prepare_connection_shutdown", 1
    )[1].split("def continue_deferred_session_action", 1)[0]

    deferred = source.split(
        "def continue_deferred_session_action", 1
    )[1].split("def finish_connection_job", 1)[0]

    finish = source.split("def finish_connection_job", 1)[1]

    assert "stop_reason: str | None = None" in prepare
    assert '"automatic_shutdown": True' in prepare
    assert '"stop_reason"' in prepare

    assert "stop_reason: str | None = None" in deferred
    assert '"stop_reason"' in deferred
    assert 'if action == "stop"' in deferred

    assert "raw_payload = dict(job.payload or {})" in finish
    assert 'raw_payload.get("stop_reason")' in finish
    assert "stop_reason=stop_reason" in finish

    # Provenance must be captured before the sensitive connection payload
    # is redacted.
    assert finish.index("raw_payload = dict(job.payload or {})") < finish.index(
        'job.payload = {"lease_id": raw_lease_id, "redacted": True}'
    )
