from pathlib import Path


def test_e2e_validation_script_is_guarded_and_disposable() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "e2e-lifecycle-validation.py").read_text()

    assert 'ORG_SLUG = "khan-cloud-validation"' in source
    assert 'NODE_NAME = "KC-E2E-VALIDATION"' in source
    assert 'MACHINE_ID = "khan-cloud-e2e-validation-node-v1"' in source
    assert "--cleanup" in source
    assert "X-Deployment-Enrollment-Code" in source
    assert "/api/v1/nodes/heartbeat" in source
    assert "/api/v1/nodes/installation-events" in source
    assert "build_operations_dashboard" in source


def test_validation_payload_contains_no_customer_contact_fields() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "e2e-lifecycle-validation.py").read_text().lower()

    assert '"email"' not in source
    assert '"phone"' not in source
    assert '"password"' not in source


def test_e2e_script_captures_ids_before_session_closes() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "e2e-lifecycle-validation.py").read_text()

    assert "organization_id = org.id" in source
    assert "deployment_profile_id = profile.id" in source
    assert "organization_id=organization_id" in source
    assert "deployment_profile_id=deployment_profile_id" in source
