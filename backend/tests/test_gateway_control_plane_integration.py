from pathlib import Path


def test_network_api_reconciles_create_when_enabled():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "api"
        / "v1"
        / "network.py"
    ).read_text()

    assert "reconcile_port_mapping_if_enabled" in source
    assert '"/ports/{mapping_id}/reconcile"' in source


def test_customer_portal_receives_non_released_mapping_lifecycle():
    root = Path(__file__).resolve().parents[1]

    gateway_source = (
        root
        / "app"
        / "services"
        / "gateway_service.py"
    ).read_text()

    portal_source = (
        root
        / "app"
        / "services"
        / "portal_service.py"
    ).read_text()

    assert 'PortMapping.status == "active"' in gateway_source
    assert "active_only=False" in portal_source
    assert 'mapping.status == "released"' in portal_source
    assert "_public_endpoint_display_status" in portal_source


def test_live_mode_remains_disabled_by_default():
    root = Path(__file__).resolve().parents[1]

    config = (
        root
        / "app"
        / "core"
        / "config.py"
    ).read_text()

    env_example = (
        root
        / ".env.example"
    ).read_text()

    assert "MIKROTIK_LIVE_ENABLED: bool = False" in config
    assert "MIKROTIK_LIVE_ENABLED=false" in env_example
