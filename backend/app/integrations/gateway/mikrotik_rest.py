from __future__ import annotations

from typing import Any

import httpx

from app.integrations.gateway.base import (
    GatewayApplyResult,
    GatewayNatRule,
)


class MikroTikGatewayError(RuntimeError):
    pass


class MikroTikRESTAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        verify_tls: bool = True,
        timeout_seconds: float = 10.0,
        live_enabled: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.live_enabled = live_enabled

        self._owns_client = client is None

        self.client = client or httpx.Client(
            base_url=self.base_url,
            auth=(username, password),
            verify=verify_tls,
            timeout=timeout_seconds,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        try:
            response = self.client.request(
                method,
                path,
                **kwargs,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MikroTikGatewayError(
                f"RouterOS request failed: {exc}"
            ) from exc

        if not response.content:
            return None

        try:
            return response.json()
        except ValueError as exc:
            raise MikroTikGatewayError(
                "RouterOS returned invalid JSON."
            ) from exc

    def _find_owned_rule(
        self,
        rule: GatewayNatRule,
    ) -> dict[str, Any] | None:
        result = self._request(
            "GET",
            "/rest/ip/firewall/nat",
            params={
                "comment": rule.ownership_tag,
            },
        )

        if not isinstance(result, list):
            raise MikroTikGatewayError(
                "Unexpected RouterOS NAT response."
            )

        if not result:
            return None

        if len(result) > 1:
            raise MikroTikGatewayError(
                "Multiple RouterOS rules use the same Khan Cloud ownership tag."
            )

        return result[0]

    @staticmethod
    def _desired_payload(
        rule: GatewayNatRule,
    ) -> dict[str, str]:
        return {
            "chain": "dstnat",
            "action": "dst-nat",
            "protocol": rule.protocol,
            "dst-address": rule.public_ip,
            "dst-port": str(rule.public_port),
            "to-addresses": rule.private_ip,
            "to-ports": str(rule.private_port),
            "comment": rule.ownership_tag,
        }

    def ensure_port_mapping(
        self,
        rule: GatewayNatRule,
    ) -> GatewayApplyResult:
        desired = self._desired_payload(rule)

        if not self.live_enabled:
            return GatewayApplyResult(
                changed=False,
                external_id=None,
                message="MikroTik live mode is disabled.",
            )

        existing = self._find_owned_rule(rule)

        if existing is None:
            created = self._request(
                "PUT",
                "/rest/ip/firewall/nat",
                json=desired,
            )

            external_id = None
            if isinstance(created, dict):
                external_id = created.get(".id")

            return GatewayApplyResult(
                changed=True,
                external_id=external_id,
                message="RouterOS NAT mapping created.",
            )

        external_id = existing.get(".id")

        if not external_id:
            raise MikroTikGatewayError(
                "Existing RouterOS NAT rule has no .id."
            )

        matches = all(
            str(existing.get(key, "")) == str(value)
            for key, value in desired.items()
        )

        if matches:
            return GatewayApplyResult(
                changed=False,
                external_id=external_id,
                message="RouterOS NAT mapping already matches desired state.",
            )

        updated = self._request(
            "PATCH",
            f"/rest/ip/firewall/nat/{external_id}",
            json=desired,
        )

        updated_id = external_id
        if isinstance(updated, dict):
            updated_id = updated.get(".id", external_id)

        return GatewayApplyResult(
            changed=True,
            external_id=updated_id,
            message="RouterOS NAT mapping reconciled.",
        )

    def remove_port_mapping(
        self,
        rule: GatewayNatRule,
    ) -> GatewayApplyResult:
        if not self.live_enabled:
            return GatewayApplyResult(
                changed=False,
                external_id=None,
                message="MikroTik live mode is disabled.",
            )

        existing = self._find_owned_rule(rule)

        if existing is None:
            return GatewayApplyResult(
                changed=False,
                external_id=None,
                message="RouterOS NAT mapping already absent.",
            )

        external_id = existing.get(".id")

        if not external_id:
            raise MikroTikGatewayError(
                "Existing RouterOS NAT rule has no .id."
            )

        self._request(
            "DELETE",
            f"/rest/ip/firewall/nat/{external_id}",
        )

        return GatewayApplyResult(
            changed=True,
            external_id=external_id,
            message="RouterOS NAT mapping removed.",
        )
