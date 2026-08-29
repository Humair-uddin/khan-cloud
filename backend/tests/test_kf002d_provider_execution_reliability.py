from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.payment_adapter_registry import (
    PaymentAdapterError,
    clear_adapter_registry_for_tests,
    create_adapter_for_provider,
    register_adapter,
    registered_adapter_types,
)
from app.services.payment_financial_outbox import (
    build_outbox_message,
)
from app.services.payment_provider_health import (
    ProviderHealthStatus,
    build_health_observation,
)
from app.services.payment_provider_policy import (
    PaymentProviderPolicyError,
    ProviderOperationPolicy,
    enforce_provider_operation,
    validate_currency_semantics,
)
from app.services.payment_secret_resolver import (
    PaymentSecretError,
    resolve_secret,
    validate_secret_reference,
)
from app.services.payment_webhook_forensics import (
    build_forensic_record,
)
from app.services.payment_webhook_outcome import (
    WebhookOutcomeCode,
    webhook_http_outcome,
)


ROOT = Path(__file__).resolve().parents[1]


def provider(**overrides):
    data = {
        "code": "merchant-pk-1",
        "adapter_type": "fake-bank",
        "enabled": True,
        "capabilities": {
            "deposits": True,
            "refunds": True,
            "payouts": False,
        },
        "supported_currencies": [
            "PKR",
            "USD",
        ],
    }

    data.update(overrides)

    return SimpleNamespace(**data)


def test_provider_policy_accepts_enabled_supported_operation():
    result = enforce_provider_operation(
        provider(),
        ProviderOperationPolicy(
            capability="refunds",
            currency="PKR",
        ),
    )

    assert result == (
        "PKR",
        "PKR",
        "PKR",
    )


def test_provider_policy_rejects_disabled_provider():
    with pytest.raises(
        PaymentProviderPolicyError
    ):
        enforce_provider_operation(
            provider(enabled=False),
            ProviderOperationPolicy(
                capability="refunds",
                currency="PKR",
            ),
        )


def test_provider_policy_rejects_missing_capability():
    with pytest.raises(
        PaymentProviderPolicyError
    ):
        enforce_provider_operation(
            provider(),
            ProviderOperationPolicy(
                capability="payouts",
                currency="PKR",
            ),
        )


def test_provider_policy_rejects_unsupported_currency():
    with pytest.raises(
        PaymentProviderPolicyError
    ):
        enforce_provider_operation(
            provider(),
            ProviderOperationPolicy(
                capability="refunds",
                currency="EUR",
            ),
        )


def test_no_silent_fx():
    with pytest.raises(
        PaymentProviderPolicyError
    ):
        validate_currency_semantics(
            transaction_currency="USD",
            presentment_currency="USD",
            settlement_currency="PKR",
            allow_explicit_fx=False,
        )


def test_explicit_fx_semantics_can_be_declared():
    assert validate_currency_semantics(
        transaction_currency="USD",
        presentment_currency="USD",
        settlement_currency="PKR",
        allow_explicit_fx=True,
    ) == (
        "USD",
        "USD",
        "PKR",
    )


def test_adapter_registry_is_keyed_by_adapter_type():
    clear_adapter_registry_for_tests()

    class FakeAdapter:
        adapter_type = "fake-bank"

        def __init__(self, provider):
            self.provider = provider

        def healthcheck(self):
            return {"ok": True}

    register_adapter(
        "fake-bank",
        lambda provider: FakeAdapter(
            provider
        ),
    )

    first = provider(
        code="merchant-account-one",
        adapter_type="fake-bank",
    )

    second = provider(
        code="merchant-account-two",
        adapter_type="fake-bank",
    )

    adapter1 = create_adapter_for_provider(
        first
    )
    adapter2 = create_adapter_for_provider(
        second
    )

    assert adapter1.provider.code == (
        "merchant-account-one"
    )

    assert adapter2.provider.code == (
        "merchant-account-two"
    )

    assert registered_adapter_types() == (
        "fake-bank",
    )


def test_adapter_registry_rejects_unknown_adapter():
    clear_adapter_registry_for_tests()

    with pytest.raises(
        PaymentAdapterError
    ):
        create_adapter_for_provider(
            provider(
                adapter_type="missing"
            )
        )


def test_env_secret_reference_is_resolved():
    os.environ[
        "KF002D_TEST_SECRET"
    ] = "temporary-test-secret"

    try:
        parsed = validate_secret_reference(
            "env:KF002D_TEST_SECRET"
        )

        assert parsed.scheme == "env"

        assert resolve_secret(
            "env:KF002D_TEST_SECRET"
        ) == "temporary-test-secret"

    finally:
        os.environ.pop(
            "KF002D_TEST_SECRET",
            None,
        )


def test_plaintext_secret_reference_is_forbidden():
    with pytest.raises(
        PaymentSecretError
    ):
        validate_secret_reference(
            "literal:do-not-store-this"
        )


def test_webhook_outcome_contract():
    invalid = webhook_http_outcome(
        WebhookOutcomeCode.INVALID_SIGNATURE
    )

    retry = webhook_http_outcome(
        WebhookOutcomeCode.RETRYABLE_FAILURE
    )

    duplicate = webhook_http_outcome(
        WebhookOutcomeCode.DUPLICATE
    )

    assert invalid.http_status == 401
    assert invalid.retryable is False

    assert retry.http_status == 503
    assert retry.retryable is True

    assert duplicate.http_status == 200
    assert duplicate.accepted is True


def test_forensic_record_never_stores_raw_signature():
    raw_signature = (
        "super-secret-signature-material"
    )

    record = build_forensic_record(
        provider_code="merchant-one",
        event_id="evt-1",
        payload={"amount": 100},
        signature=raw_signature,
        outcome_code="invalid_signature",
        http_status=401,
        retryable=False,
        error=ValueError(
            "bad signature"
        ),
    )

    assert record.signature_fingerprint
    assert (
        raw_signature
        not in record.signature_fingerprint
    )

    assert len(
        record.signature_fingerprint
    ) == 64


def test_outbox_content_hash_is_stable():
    one = build_outbox_message(
        event_type="payout.execute",
        aggregate_type="payout",
        aggregate_id="pay-1",
        idempotency_key="outbox:pay-1",
        payload={
            "amount_minor": 100,
            "currency": "PKR",
        },
    )

    two = build_outbox_message(
        event_type="payout.execute",
        aggregate_type="payout",
        aggregate_id="pay-1",
        idempotency_key="outbox:pay-1",
        payload={
            "currency": "PKR",
            "amount_minor": 100,
        },
    )

    assert one.payload_hash == two.payload_hash


def test_provider_health_contract():
    observation = build_health_observation(
        provider_code="merchant-one",
        status=ProviderHealthStatus.HEALTHY,
        latency_ms=25,
        details={"probe": "api"},
    )

    assert observation.latency_ms == 25
    assert (
        observation.status
        == ProviderHealthStatus.HEALTHY
    )


def test_reliability_migration_contract():
    migration = (
        ROOT
        / "migrations"
        / "versions"
        / (
            "f2a002d10001_"
            "provider_execution_reliability_v1.py"
        )
    ).read_text()

    assert (
        'revision = "f2a002d10001"'
        in migration
    )

    assert (
        'down_revision = "f2a002c10001"'
        in migration
    )

    assert (
        "payment_webhook_forensic_events"
        in migration
    )

    assert (
        "payment_provider_health_events"
        in migration
    )

    assert (
        "payment_financial_outbox"
        in migration
    )

    assert (
        "uq_payment_financial_outbox_idempotency"
        in migration
    )


def test_provider_specific_layer_does_not_mutate_balances():
    source_files = [
        ROOT
        / "app"
        / "services"
        / "payment_provider_policy.py",

        ROOT
        / "app"
        / "services"
        / "payment_adapter_registry.py",

        ROOT
        / "app"
        / "services"
        / "payment_secret_resolver.py",

        ROOT
        / "app"
        / "services"
        / "payment_webhook_forensics.py",

        ROOT
        / "app"
        / "services"
        / "payment_financial_outbox.py",
    ]

    joined = "\n".join(
        path.read_text()
        for path in source_files
    )

    assert "balance_minor +=" not in joined
    assert "balance_minor -=" not in joined


def test_provider_specific_layer_has_no_direct_ledger_sql():
    source_files = list(
        (
            ROOT
            / "app"
            / "services"
        ).glob("payment_*.py")
    )

    joined = "\n".join(
        path.read_text().lower()
        for path in source_files
    )

    forbidden = [
        "insert into ledger_entries",
        "insert into ledger_transactions",
        "update ledger_entries",
        "update ledger_transactions",
        "delete from ledger_entries",
        "delete from ledger_transactions",
    ]

    for expression in forbidden:
        assert expression not in joined
