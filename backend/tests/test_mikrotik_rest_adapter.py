import json
from uuid import uuid4

import httpx

from app.integrations.gateway.base import GatewayNatRule
from app.integrations.gateway.mikrotik_rest import (
    MikroTikRESTAdapter,
)


def rule() -> GatewayNatRule:
    return GatewayNatRule(
        mapping_id=uuid4(),
        public_ip="203.0.113.10",
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
