from pathlib import Path

from app.services import rbac_service


def test_gateway_permissions_exist():
    assert (
        "network.gateways.read"
        in rbac_service.DEFAULT_PERMISSIONS
    )

    assert (
        "network.gateways.manage"
        in rbac_service.DEFAULT_PERMISSIONS
    )


def test_operator_can_manage_gateways():
    permissions = rbac_service.DEFAULT_ROLES["operator"]

    assert "network.gateways.read" in permissions
    assert "network.gateways.manage" in permissions


def test_customer_does_not_manage_gateway_inventory():
    permissions = rbac_service.DEFAULT_ROLES["customer"]

    assert "network.gateways.read" not in permissions
    assert "network.gateways.manage" not in permissions


def test_network_api_has_gateway_routes():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "api"
        / "v1"
        / "network.py"
    ).read_text()

    assert '"/gateways"' in source
    assert '"network.gateways.read"' in source
    assert '"network.gateways.manage"' in source


def test_network_api_has_vps_port_routes():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "api"
        / "v1"
        / "network.py"
    ).read_text()

    assert '"/vps/{vps_id}/ports"' in source
    assert '"/ports/{mapping_id}"' in source
    assert '"vps.read"' in source
    assert '"vps.manage"' in source


def test_port_mapping_create_requires_gateway_id():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "schemas"
        / "network.py"
    ).read_text()

    assert "gateway_id: UUID" in source
