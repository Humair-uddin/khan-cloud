from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import gateway_service


def test_protocol_normalization():
    assert gateway_service._normalize_protocol("TCP") == "tcp"
    assert gateway_service._normalize_protocol(" udp ") == "udp"

    with pytest.raises(gateway_service.GatewayError):
        gateway_service._normalize_protocol("icmp")


def test_ip_validation():
    assert gateway_service._validate_ip("192.168.250.10") == "192.168.250.10"

    with pytest.raises(gateway_service.GatewayError):
        gateway_service._validate_ip("not-an-ip")


def test_next_available_port_skips_used(monkeypatch):
    monkeypatch.setattr(
        gateway_service,
        "_used_ports",
        lambda db, gateway_id, protocol: {20000, 20001},
    )

    assert (
        gateway_service._next_available_port(
            object(),
            gateway_id=uuid4(),
            protocol="tcp",
            start=20000,
            end=20010,
        )
        == 20002
    )


def test_next_available_port_exhaustion(monkeypatch):
    monkeypatch.setattr(
        gateway_service,
        "_used_ports",
        lambda db, gateway_id, protocol: {20000, 20001},
    )

    with pytest.raises(
        gateway_service.GatewayError,
        match="No public ports",
    ):
        gateway_service._next_available_port(
            object(),
            gateway_id=uuid4(),
            protocol="tcp",
            start=20000,
            end=20001,
        )


def test_gateway_schema_has_partial_unique_active_endpoint():
    root = Path(__file__).resolve().parents[1]
    model = (root / "app" / "models" / "gateway.py").read_text()

    assert "uq_port_mapping_active_endpoint" in model
    assert "status <> 'released'" in model
    assert "public_port BETWEEN 1 AND 65535" in model
    assert "private_port BETWEEN 1 AND 65535" in model


def test_gateway_migration_is_surgical():
    root = Path(__file__).resolve().parents[1]
    migration = (
        root
        / "migrations"
        / "versions"
        / "c75f8d75b793_public_gateway_and_port_mappings.py"
    ).read_text()

    assert 'op.create_table(\n        "public_gateways"' in migration
    assert 'op.create_table(\n        "port_mappings"' in migration
    assert "uq_port_mapping_active_endpoint" in migration

    # Guard against the unsafe first autogeneration returning.
    assert 'op.drop_table("audit_events")' not in migration
    assert "commercial_quotes" not in migration
    assert "customer_orders" not in migration
    assert "node_capacities" not in migration
