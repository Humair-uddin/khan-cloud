from pathlib import Path

from app.services.portal_service import (
    _public_endpoint_display_status,
)


def test_portal_schema_exposes_sanitized_public_endpoints():
    root = Path(__file__).resolve().parents[1]

    schema = (
        root
        / "app"
        / "schemas"
        / "portal.py"
    ).read_text()

    assert "class PortalPublicEndpointRead" in schema
    assert "public_ip: str" in schema
    assert "public_port: int" in schema
    assert "private_port: int" in schema
    assert "status: str" in schema
    assert "display_status: str" in schema

    assert "gateway_id" not in schema
    assert "provider" not in schema
    assert "gateway_type" not in schema
    assert "external_id" not in schema
    assert "reconcile_error" not in schema


def test_portal_service_uses_gateway_mapping_service():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "services"
        / "portal_service.py"
    ).read_text()

    assert "list_vps_port_mappings" in source
    assert "get_public_gateway" in source
    assert "public_endpoints=public_endpoints" in source


def test_portal_lists_non_released_mapping_lifecycle():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "services"
        / "portal_service.py"
    ).read_text()

    assert "active_only=False" in source
    assert 'mapping.status == "released"' in source


def test_endpoint_display_status_is_customer_safe():
    assert (
        _public_endpoint_display_status("pending")
        == "Configuring"
    )
    assert (
        _public_endpoint_display_status("active")
        == "Ready"
    )
    assert (
        _public_endpoint_display_status("failed")
        == "Retrying"
    )
    assert (
        _public_endpoint_display_status("releasing")
        == "Removing"
    )
    assert (
        _public_endpoint_display_status("unexpected")
        == "Unavailable"
    )
