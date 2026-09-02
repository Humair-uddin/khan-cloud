from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _service() -> str:
    return (
        ROOT
        / "app"
        / "services"
        / "gaming_service.py"
    ).read_text()


def test_d1_backend_requires_v2_ownership_proof():
    source = _service()

    assert "ownership_schema_version" in source
    assert "ownership_boundary_verified" in source
    assert "termination_verified" in source
    assert "owned_process_count_remaining" in source
    assert "and ownership_ok" in source


def test_d1_plain_legacy_v1_cannot_repool():
    source = _service()

    assert "ownership_schema_version < 2" not in source
    assert "legacy_retirement_ok" in source
    assert "structural_ownership_ok" in source
    assert "legacy_retirement_expected_state_sha256" in source
    assert "destructive_pid_termination_performed" in source


def test_d1_does_not_bypass_c9_host_revalidation():
    source = _service()

    assert "gaming_host_readiness_reasons" in source
    assert "gaming_recovery_readiness_reasons" in source
    assert "host_revalidated = not readiness_reasons" in source
    assert "release_gaming_reservation(db, session)" in source



def test_legacy_retirement_reuses_existing_release_authority():
    source = _service()

    assert "def queue_gaming_legacy_retirement(" in source
    assert 'job_type="gaming.session.delete"' in source
    assert '"legacy_retirement": True' in source
    assert "record_audit_event(" in source
    assert 'action="gaming.legacy_retirement_queued"' in source
    assert "release_gaming_reservation(db, session)" in source


def test_d1_operator_quarantine_recovery_preserves_legacy_authorization():
    service = (
        (Path(__file__).resolve().parents[1] / "app/services/gaming_service.py")
        .read_text(encoding="utf-8")
    )
    section = service.split(
        "def queue_gaming_quarantine_recovery", 1
    )[1].split(
        "def reconcile_quarantined_gaming_sessions_for_node", 1
    )[0]

    assert 'candidate.payload.get("legacy_retirement") is True' in section
    assert 'if source != "operator":' in section
    assert "if actor_user_id is None:" in section
    # Only the original operator-authorized legacy retirement is an
    # authorization root. Failed recovery descendants inherit that authority
    # and must not become additional roots.
    assert "legacy_authorization_roots = [" in section
    assert '"legacy_retirement_origin_job_id"' in section
    assert "if len(legacy_authorization_roots) != 1:" in section
    assert "origin = legacy_authorization_roots[0]" in section
    assert "if len(legacy_jobs) != 1:" not in section

    for field in (
        "legacy_retirement_expected_state_sha256",
        "legacy_runtime_id",
        "legacy_runtime_started_at",
        "legacy_retirement_reason",
        "legacy_retirement_origin_job_id",
        "legacy_retirement_recovery_requested_by_user_id",
    ):
        assert field in section

    assert 'legacy_authorization = {' in section
    assert '"legacy_retirement": True' in section
    assert "recovery_payload.update(legacy_authorization)" in section


def test_d1_automatic_recovery_cannot_inherit_legacy_operator_authority():
    service = (
        (Path(__file__).resolve().parents[1] / "app/services/gaming_service.py")
        .read_text(encoding="utf-8")
    )
    section = service.split(
        "def queue_gaming_quarantine_recovery", 1
    )[1].split(
        "def reconcile_quarantined_gaming_sessions_for_node", 1
    )[0]

    assert "if legacy_jobs:" in section
    assert 'if source != "operator":' in section
    assert (
        "Legacy runtime quarantine recovery requires explicit "
        in section
    )


def test_d1_ordinary_quarantine_recovery_contract_remains_present():
    service = (
        (Path(__file__).resolve().parents[1] / "app/services/gaming_service.py")
        .read_text(encoding="utf-8")
    )
    section = service.split(
        "def queue_gaming_quarantine_recovery", 1
    )[1].split(
        "def reconcile_quarantined_gaming_sessions_for_node", 1
    )[0]

    assert '"quarantine_recovery": True' in section
    assert '"recovery_source": source' in section
    assert '"recovery_attempt": session.quarantine_recovery_attempt_count' in section
    assert "recovery_payload.update(legacy_authorization)" in section
