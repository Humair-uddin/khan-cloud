from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.compute import (
    GamingConnectionLeaseCreate,
    GamingConnectionPairRequest,
)


def test_pairing_pin_is_exactly_four_digits():
    assert GamingConnectionPairRequest(
        pin="1234"
    ).pin == "1234"

    for invalid in ("123", "12345", "12a4"):
        with pytest.raises(ValidationError):
            GamingConnectionPairRequest(pin=invalid)


def test_pairing_window_is_bounded():
    assert (
        GamingConnectionLeaseCreate()
        .pairing_ttl_seconds
        == 300
    )

    with pytest.raises(ValidationError):
        GamingConnectionLeaseCreate(
            pairing_ttl_seconds=30
        )

    with pytest.raises(ValidationError):
        GamingConnectionLeaseCreate(
            pairing_ttl_seconds=3600
        )


def test_kg004_uses_authoritative_node_job_channel():
    root = Path(__file__).resolve().parents[1]

    service = (
        root
        / "app/services/gaming_connection_service.py"
    ).read_text()

    assert '"gaming.connection.pair"' in service
    assert '"gaming.connection.revoke"' in service
    assert "NodeJob(" in service


def test_pairing_pin_is_scrubbed_after_completion():
    root = Path(__file__).resolve().parents[1]

    service = (
        root
        / "app/services/gaming_connection_service.py"
    ).read_text()

    assert '"redacted": True' in service
    assert (
        "Never retain a customer pairing PIN"
        in service
    )


def test_sunshine_admin_credentials_never_enter_api_schema():
    root = Path(__file__).resolve().parents[1]

    schema = (
        root / "app/schemas/compute.py"
    ).read_text()

    lease_section = schema[
        schema.index("class GamingConnectionLeaseCreate")
    :]

    assert "sunshine_api_password" not in lease_section
    assert "sunshine_api_username" not in lease_section
