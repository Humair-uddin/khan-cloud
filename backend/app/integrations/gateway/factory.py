from __future__ import annotations

from app.integrations.gateway.base import GatewayNatRule
from app.models.gateway import PortMapping, PublicGateway


def nat_rule_from_models(
    *,
    gateway: PublicGateway,
    mapping: PortMapping,
) -> GatewayNatRule:
    return GatewayNatRule(
        mapping_id=mapping.id,
        public_ip=gateway.public_ip,
        protocol=mapping.protocol,
        public_port=mapping.public_port,
        private_ip=mapping.private_ip,
        private_port=mapping.private_port,
    )
