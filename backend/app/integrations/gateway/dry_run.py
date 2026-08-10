from __future__ import annotations

from app.integrations.gateway.base import (
    GatewayApplyResult,
    GatewayNatRule,
)


class DryRunGatewayAdapter:
    def __init__(self) -> None:
        self._rules: dict[str, GatewayNatRule] = {}

    def ensure_port_mapping(
        self,
        rule: GatewayNatRule,
    ) -> GatewayApplyResult:
        key = rule.ownership_tag
        existing = self._rules.get(key)

        if existing == rule:
            return GatewayApplyResult(
                changed=False,
                external_id=key,
                message="Mapping already matches desired state.",
            )

        self._rules[key] = rule

        return GatewayApplyResult(
            changed=True,
            external_id=key,
            message="Dry-run mapping applied.",
        )

    def remove_port_mapping(
        self,
        rule: GatewayNatRule,
    ) -> GatewayApplyResult:
        key = rule.ownership_tag

        if key not in self._rules:
            return GatewayApplyResult(
                changed=False,
                external_id=None,
                message="Mapping already absent.",
            )

        del self._rules[key]

        return GatewayApplyResult(
            changed=True,
            external_id=key,
            message="Dry-run mapping removed.",
        )

    def list_rules(self) -> list[GatewayNatRule]:
        return list(self._rules.values())
