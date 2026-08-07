from types import SimpleNamespace
from uuid import uuid4

from app.schemas.installation_event import InstallationEventCreate
from app.services.installation_telemetry_service import sanitize_details, sanitize_message


def test_sensitive_message_values_are_redacted() -> None:
    value = sanitize_message("token=abc123 password=hunter2 ordinary text")
    assert "abc123" not in value
    assert "hunter2" not in value
    assert "[REDACTED]" in value


def test_details_are_allowlisted_and_sensitive_keys_removed() -> None:
    result = sanitize_details({
        "current_stage": "preflight",
        "installer_version": "1.0.0",
        "token": "never-send-this",
        "arbitrary_machine_data": "blocked",
        "timed_out": False,
    })
    assert result == {
        "current_stage": "preflight",
        "installer_version": "1.0.0",
        "timed_out": False,
    }


def test_telemetry_schema_is_operational_not_customer_identity() -> None:
    payload = InstallationEventCreate(
        transaction_id=str(uuid4()),
        feature_pack_id="FP-TEST",
        feature_pack_version="1.0.0",
        status="failed",
        stage="preflight",
        failure_category="preflight",
        message="compatibility failure",
        details={"current_stage": "preflight"},
    )
    data = payload.model_dump()
    assert "email" not in data
    assert "phone" not in data
    assert "customer" not in data
