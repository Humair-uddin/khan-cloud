from pathlib import Path


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

    assert "gateway_id" not in schema
    assert "provider" not in schema
    assert "gateway_type" not in schema


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


def test_portal_only_lists_active_mappings():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "app"
        / "services"
        / "portal_service.py"
    ).read_text()

    assert "active_only=True" in source
