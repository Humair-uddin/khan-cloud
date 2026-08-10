from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.integrations.gateway.factory import nat_rule_from_models


def test_factory_preserves_public_ip_and_upstream_topology():
    gateway = SimpleNamespace(
        public_ip="124.29.197.4",
        ingress_mode="upstream_nat",
        wan_interface="WAN1",
    )

    mapping = SimpleNamespace(
        id=uuid4(),
        protocol="tcp",
        public_port=29998,
        private_ip="10.10.20.100",
        private_port=18080,
    )

    rule = nat_rule_from_models(
        gateway=gateway,
        mapping=mapping,
    )

    assert rule.public_ip == "124.29.197.4"
    assert rule.ingress_mode == "upstream_nat"
    assert rule.wan_interface == "WAN1"


def test_gateway_model_contains_ingress_constraint():
    root = Path(__file__).resolve().parents[1]

    source = (
        root
        / "app"
        / "models"
        / "gateway.py"
    ).read_text()

    assert "ck_public_gateway_ingress_mode" in source
    assert "upstream_nat" in source


def test_gateway_migration_adds_ingress_topology():
    root = Path(__file__).resolve().parents[1]

    migration = (
        root
        / "migrations"
        / "versions"
        / "f19c4e7a2b31_gateway_ingress_topology.py"
    ).read_text()

    assert '"ingress_mode"' in migration
    assert '"wan_interface"' in migration
    assert "ck_public_gateway_ingress_mode" in migration
