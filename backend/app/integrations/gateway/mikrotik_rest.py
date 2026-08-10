from __future__ import annotations

import ssl
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
        ca_file: str | None = None,
        timeout_seconds: float = 10.0,
        live_enabled: bool = False,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.live_enabled = live_enabled

        self._owns_client = client is None

        verify: bool | ssl.SSLContext

        if verify_tls:
            verify = ssl.create_default_context(
                cafile=ca_file,
            ) if ca_file else True
        else:
            verify = False

        self.client = client or httpx.Client(
            base_url=self.base_url,
            auth=(username, password),
            verify=verify,
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
        payload = {
            "chain": "dstnat",
            "action": "dst-nat",
            "protocol": rule.protocol,
            "dst-port": str(rule.public_port),
            "to-addresses": rule.private_ip,
            "to-ports": str(rule.private_port),
            "comment": rule.ownership_tag,
        }

        if rule.ingress_mode == "direct":
            payload["dst-address"] = rule.public_ip
        elif rule.ingress_mode == "upstream_nat":
            if not rule.wan_interface:
                raise MikroTikGatewayError(
                    "upstream_nat gateway requires wan_interface."
                )
            payload["in-interface"] = rule.wan_interface
        else:
            raise MikroTikGatewayError(
                f"Unsupported gateway ingress mode: "
                f"{rule.ingress_mode}"
            )

        return payload

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

        # Desired payload must also not leave behind an obsolete
        # mutually-exclusive ingress selector.
        if rule.ingress_mode == "direct":
            selector_matches = not existing.get("in-interface")
        else:
            selector_matches = not existing.get("dst-address")

        if matches and selector_matches:
            return GatewayApplyResult(
                changed=False,
                external_id=external_id,
                message="RouterOS NAT mapping already matches desired state.",
            )

        existing_direct = bool(existing.get("dst-address"))
        existing_upstream = bool(existing.get("in-interface"))

        topology_changed = (
            rule.ingress_mode == "direct"
            and existing_upstream
        ) or (
            rule.ingress_mode == "upstream_nat"
            and existing_direct
        )

        if topology_changed:
            # RouterOS PATCH/set cannot safely express removal of an
            # obsolete selector by assigning an empty string. Replace
            # the Khan Cloud-owned rule instead.
            self._request(
                "DELETE",
                f"/rest/ip/firewall/nat/{external_id}",
            )

            created = self._request(
                "PUT",
                "/rest/ip/firewall/nat",
                json=desired,
            )

            replacement_id = None
            if isinstance(created, dict):
                replacement_id = created.get(".id")

            return GatewayApplyResult(
                changed=True,
                external_id=replacement_id,
                message=(
                    "RouterOS NAT mapping replaced for "
                    "ingress topology change."
                ),
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
