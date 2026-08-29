import json
import time

import pytest

from app.schemas.payment_provider import NormalizedPaymentEvent
from app.services.payment_provider_registry import (
    PaymentAdapterError,
    ProviderCapabilities,
    clear_adapter_registry_for_tests,
    get_adapter,
    register_adapter,
    registered_adapter_codes,
)
from app.services.payment_webhook_service import (
    PaymentWebhookError,
    canonical_event_hash,
    validate_event_timestamp,
)


class FakeAdapter:
    code = "fake"
    capabilities = ProviderCapabilities(
        deposits=True,
        refunds=True,
        chargebacks=True,
        payouts=True,
        treasury_settlement=True,
    )

    def verify_webhook(
        self,
        *,
        raw_body,
        headers,
        secret,
    ):
        return secret == "secret"

    def normalize_webhook(
        self,
        *,
        raw_body,
        headers,
    ):
        payload = json.loads(raw_body)
        return NormalizedPaymentEvent(**payload)


def test_registry_requires_unique_provider_code():
    clear_adapter_registry_for_tests()

    adapter = FakeAdapter()
    register_adapter(adapter)

    assert registered_adapter_codes() == ("fake",)
    assert get_adapter("FAKE") is adapter

    with pytest.raises(PaymentAdapterError):
        register_adapter(adapter)


def test_event_currency_normalization():
    event = NormalizedPaymentEvent(
        provider="fake",
        event_id="evt-1",
        event_type="deposit.succeeded",
        provider_timestamp=int(time.time()),
        amount_minor=100,
        currency="pkr",
        presentment_currency="usd",
        settlement_currency="pkr",
    )

    assert event.currency == "PKR"
    assert event.presentment_currency == "USD"
    assert event.settlement_currency == "PKR"


def test_event_hash_is_content_bound():
    base = dict(
        provider="fake",
        event_id="evt-1",
        event_type="deposit.succeeded",
        provider_timestamp=1000,
        amount_minor=100,
        currency="PKR",
    )

    a = NormalizedPaymentEvent(**base)
    b = NormalizedPaymentEvent(
        **{**base, "amount_minor": 101}
    )

    assert canonical_event_hash(a) != canonical_event_hash(b)


def test_timestamp_replay_window():
    validate_event_timestamp(
        event_timestamp=1000,
        tolerance_seconds=300,
        now=1200,
    )

    with pytest.raises(PaymentWebhookError):
        validate_event_timestamp(
            event_timestamp=1000,
            tolerance_seconds=300,
            now=1401,
        )


def test_provider_namespace_is_not_network_gateway():
    from app.models.payment_provider import PaymentProvider

    assert PaymentProvider.__tablename__ == "payment_providers"
