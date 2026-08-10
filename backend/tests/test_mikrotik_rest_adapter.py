import pytest
import json
from uuid import UUID, uuid4

import httpx

from app.integrations.gateway.base import GatewayNatRule
from app.integrations.gateway.mikrotik_rest import (
    MikroTikGatewayError,
    MikroTikRESTAdapter,
)


def rule() -> GatewayNatRule:
    return GatewayNatRule(
        mapping_id=uuid4(),
        public_ip="203.0.113.10",
        ingress_mode="direct",
        wan_interface=None,
        protocol="tcp",
        public_port=22001,
        private_ip="192.168.250.10",
        private_port=22,
    )


def test_live_mode_is_disabled_by_default():
    adapter = MikroTikRESTAdapter(
        base_url="https://router.invalid",
        username="test",
        password="test",
    )

    try:
        result = adapter.ensure_port_mapping(rule())
        assert result.changed is False
        assert result.message == "MikroTik live mode is disabled."
    finally:
        adapter.close()


def test_create_nat_rule_with_mock_transport():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.method == "GET":
            return httpx.Response(200, json=[])

        if request.method == "PUT":
            payload = json.loads(request.content)
            assert payload["chain"] == "dstnat"
            assert payload["action"] == "dst-nat"
            assert payload["dst-port"] == "22001"
            assert payload["to-addresses"] == "192.168.250.10"
            assert payload["to-ports"] == "22"
            assert payload["comment"].startswith(
                "khan-cloud:port-mapping:"
            )

            return httpx.Response(
                200,
                json={".id": "*AB"},
            )

        raise AssertionError(request.method)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://router.invalid",
    )

    adapter = MikroTikRESTAdapter(
        base_url="https://router.invalid",
        username="test",
        password="test",
        live_enabled=True,
        client=client,
    )

    result = adapter.ensure_port_mapping(rule())

    assert result.changed is True
    assert result.external_id == "*AB"
    assert [x.method for x in requests] == ["GET", "PUT"]


def test_existing_matching_rule_is_idempotent():
    r = rule()

    desired = {
        ".id": "*1",
        "chain": "dstnat",
        "action": "dst-nat",
        "protocol": r.protocol,
        "dst-address": r.public_ip,
        "dst-port": str(r.public_port),
        "to-addresses": r.private_ip,
        "to-ports": str(r.private_port),
        "comment": r.ownership_tag,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json=[desired])

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://router.invalid",
    )

    adapter = MikroTikRESTAdapter(
        base_url="https://router.invalid",
        username="test",
        password="test",
        live_enabled=True,
        client=client,
    )

    result = adapter.ensure_port_mapping(r)

    assert result.changed is False
    assert result.external_id == "*1"


def test_remove_is_idempotent_when_absent():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, json=[])

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://router.invalid",
    )

    adapter = MikroTikRESTAdapter(
        base_url="https://router.invalid",
        username="test",
        password="test",
        live_enabled=True,
        client=client,
    )

    result = adapter.remove_port_mapping(rule())

    assert result.changed is False



def test_adapter_accepts_explicit_ca_file(monkeypatch):
    calls = []
    real_create_default_context = __import__("ssl").create_default_context

    def recording_context(*args, **kwargs):
        calls.append(kwargs.get("cafile"))
        return real_create_default_context(*args, **kwargs)

    monkeypatch.setattr(
        "app.integrations.gateway.mikrotik_rest.ssl.create_default_context",
        recording_context,
    )

    adapter = MikroTikRESTAdapter(
        base_url="https://router.invalid",
        username="test",
        password="test",
        verify_tls=True,
        ca_file="/etc/ssl/certs/ca-certificates.crt",
        live_enabled=False,
    )

    try:
        assert "/etc/ssl/certs/ca-certificates.crt" in calls
    finally:
        adapter.close()


def test_direct_ingress_matches_public_destination():
    rule = GatewayNatRule(
        mapping_id=uuid4(),
        public_ip="203.0.113.10",
        ingress_mode="direct",
        wan_interface=None,
        protocol="tcp",
        public_port=22001,
        private_ip="10.10.10.50",
        private_port=22,
    )

    payload = MikroTikRESTAdapter._desired_payload(rule)

    assert payload["dst-address"] == "203.0.113.10"
    assert "in-interface" not in payload


def test_upstream_nat_ingress_matches_wan_interface():
    rule = GatewayNatRule(
        mapping_id=uuid4(),
        public_ip="124.29.197.4",
        ingress_mode="upstream_nat",
        wan_interface="WAN1",
        protocol="tcp",
        public_port=29998,
        private_ip="10.10.20.100",
        private_port=18080,
    )

    payload = MikroTikRESTAdapter._desired_payload(rule)

    assert payload["in-interface"] == "WAN1"
    assert "dst-address" not in payload
    assert payload["dst-port"] == "29998"
    assert payload["to-addresses"] == "10.10.20.100"
    assert payload["to-ports"] == "18080"


def test_upstream_nat_requires_wan_interface():
    rule = GatewayNatRule(
        mapping_id=uuid4(),
        public_ip="124.29.197.4",
        ingress_mode="upstream_nat",
        wan_interface=None,
        protocol="tcp",
        public_port=29998,
        private_ip="10.10.20.100",
        private_port=18080,
    )

    with pytest.raises(
        MikroTikGatewayError,
        match="requires wan_interface",
    ):
        MikroTikRESTAdapter._desired_payload(rule)


def test_direct_to_upstream_nat_replaces_owned_rule():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                request.method,
                request.url.path,
            )
        )

        if request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        ".id": "*9",
                        "chain": "dstnat",
                        "action": "dst-nat",
                        "protocol": "tcp",
                        "dst-address": "124.29.197.4",
                        "dst-port": "29998",
                        "to-addresses": "10.10.20.100",
                        "to-ports": "18080",
                        "comment": (
                            "khan-cloud:port-mapping:"
                            "00000000-0000-0000-0000-000000000009"
                        ),
                    }
                ],
            )

        if request.method == "DELETE":
            return httpx.Response(204)

        if request.method == "PUT":
            return httpx.Response(
                201,
                json={".id": "*A"},
            )

        return httpx.Response(
            500,
            json={"error": "unexpected request"},
        )

    client = httpx.Client(
        base_url="https://router.invalid",
        transport=httpx.MockTransport(handler),
    )

    adapter = MikroTikRESTAdapter(
        base_url="https://router.invalid",
        username="test",
        password="test",
        live_enabled=True,
        client=client,
    )

    rule = GatewayNatRule(
        mapping_id=UUID(
            "00000000-0000-0000-0000-000000000009"
        ),
        public_ip="124.29.197.4",
        ingress_mode="upstream_nat",
        wan_interface="WAN1",
        protocol="tcp",
        public_port=29998,
        private_ip="10.10.20.100",
        private_port=18080,
    )

    try:
        result = adapter.ensure_port_mapping(rule)
    finally:
        client.close()

    methods = [method for method, _ in requests]

    assert result.changed is True
    assert result.external_id == "*A"
    assert "DELETE" in methods
    assert "PUT" in methods
    assert "PATCH" not in methods


def test_same_topology_change_uses_patch():
    requests = []

    mapping_id = UUID(
        "00000000-0000-0000-0000-000000000010"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.method)

        if request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        ".id": "*B",
                        "chain": "dstnat",
                        "action": "dst-nat",
                        "protocol": "tcp",
                        "in-interface": "WAN1",
                        "dst-port": "29998",
                        "to-addresses": "10.10.20.100",
                        "to-ports": "18080",
                        "comment": (
                            f"khan-cloud:port-mapping:{mapping_id}"
                        ),
                    }
                ],
            )

        if request.method == "PATCH":
            return httpx.Response(
                200,
                json={".id": "*B"},
            )

        return httpx.Response(
            500,
            json={"error": "unexpected request"},
        )

    client = httpx.Client(
        base_url="https://router.invalid",
        transport=httpx.MockTransport(handler),
    )

    adapter = MikroTikRESTAdapter(
        base_url="https://router.invalid",
        username="test",
        password="test",
        live_enabled=True,
        client=client,
    )

    rule = GatewayNatRule(
        mapping_id=mapping_id,
        public_ip="124.29.197.4",
        ingress_mode="upstream_nat",
        wan_interface="WAN1",
        protocol="tcp",
        public_port=29998,
        private_ip="10.10.20.100",
        private_port=18081,
    )

    try:
        result = adapter.ensure_port_mapping(rule)
    finally:
        client.close()

    assert result.changed is True
    assert "PATCH" in requests
    assert "DELETE" not in requests
