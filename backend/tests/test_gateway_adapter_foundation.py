from uuid import uuid4

from app.integrations.gateway.base import GatewayNatRule
from app.integrations.gateway.dry_run import DryRunGatewayAdapter


def make_rule() -> GatewayNatRule:
    return GatewayNatRule(
        mapping_id=uuid4(),
        public_ip="203.0.113.10",
        protocol="tcp",
        public_port=22001,
        private_ip="192.168.250.10",
        private_port=22,
    )


def test_rule_has_stable_khan_cloud_ownership_tag():
    rule = make_rule()

    assert rule.ownership_tag == (
        f"khan-cloud:port-mapping:{rule.mapping_id}"
    )


def test_dry_run_create_is_idempotent():
    adapter = DryRunGatewayAdapter()
    rule = make_rule()

    first = adapter.ensure_port_mapping(rule)
    second = adapter.ensure_port_mapping(rule)

    assert first.changed is True
    assert second.changed is False
    assert len(adapter.list_rules()) == 1


def test_dry_run_updates_desired_mapping():
    adapter = DryRunGatewayAdapter()
    rule = make_rule()

    adapter.ensure_port_mapping(rule)

    changed = GatewayNatRule(
        mapping_id=rule.mapping_id,
        public_ip=rule.public_ip,
        protocol=rule.protocol,
        public_port=rule.public_port,
        private_ip=rule.private_ip,
        private_port=2222,
    )

    result = adapter.ensure_port_mapping(changed)

    assert result.changed is True
    assert adapter.list_rules()[0].private_port == 2222


def test_dry_run_delete_is_idempotent():
    adapter = DryRunGatewayAdapter()
    rule = make_rule()

    adapter.ensure_port_mapping(rule)

    first = adapter.remove_port_mapping(rule)
    second = adapter.remove_port_mapping(rule)

    assert first.changed is True
    assert second.changed is False
    assert adapter.list_rules() == []


def test_adapter_does_not_require_live_router():
    adapter = DryRunGatewayAdapter()

    assert adapter.list_rules() == []
