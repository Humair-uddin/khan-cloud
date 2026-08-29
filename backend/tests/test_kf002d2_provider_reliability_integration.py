from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.payment_reliability import (
    PaymentFinancialOutbox,
    PaymentProviderHealthEvent,
    PaymentWebhookForensicEvent,
)
from app.services.payment_provider_policy import (
    PaymentProviderPolicyError,
    ProviderOperationPolicy,
    enforce_provider_operation,
)
from app.services.payment_secret_resolver import (
    PaymentSecretError,
    validate_secret_reference,
)
from app.services.payment_webhook_outcome import (
    WebhookOutcomeCode,
    webhook_http_outcome,
)


ROOT = Path(__file__).resolve().parents[1]


def real_orm_shape(**overrides):
    values = {
        "code": "merchant-one",
        "adapter_type": "fake-bank",
        "enabled": True,
        "capabilities_json": {
            "deposits": True,
            "refunds": True,
            "chargebacks": True,
            "payouts": True,
            "treasury_settlement": True,
        },
        "supported_currencies_json": [
            "PKR",
            "USD",
        ],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_policy_reads_real_payment_provider_orm_fields():
    assert enforce_provider_operation(
        real_orm_shape(),
        ProviderOperationPolicy(
            capability="refunds",
            currency="PKR",
        ),
    ) == (
        "PKR",
        "PKR",
        "PKR",
    )


def test_real_orm_capability_is_enforced():
    provider = real_orm_shape(
        capabilities_json={
            "deposits": True,
            "refunds": False,
        }
    )

    with pytest.raises(
        PaymentProviderPolicyError
    ):
        enforce_provider_operation(
            provider,
            ProviderOperationPolicy(
                capability="refunds",
                currency="PKR",
            ),
        )


def test_real_orm_supported_currency_is_enforced():
    with pytest.raises(
        PaymentProviderPolicyError
    ):
        enforce_provider_operation(
            real_orm_shape(),
            ProviderOperationPolicy(
                capability="refunds",
                currency="EUR",
            ),
        )


def test_reliability_orm_tables_match_migration():
    assert (
        PaymentWebhookForensicEvent.__tablename__
        == "payment_webhook_forensic_events"
    )
    assert (
        PaymentProviderHealthEvent.__tablename__
        == "payment_provider_health_events"
    )
    assert (
        PaymentFinancialOutbox.__tablename__
        == "payment_financial_outbox"
    )


def test_plaintext_secret_reference_remains_forbidden():
    with pytest.raises(PaymentSecretError):
        validate_secret_reference(
            "plaintext:forbidden"
        )


def test_deterministic_outcome_statuses():
    assert webhook_http_outcome(
        WebhookOutcomeCode.INVALID_SIGNATURE
    ).http_status == 401

    assert webhook_http_outcome(
        WebhookOutcomeCode.CONTENT_CONFLICT
    ).http_status == 409

    assert webhook_http_outcome(
        WebhookOutcomeCode.INTERNAL_FAILURE
    ).http_status == 500


def test_webhook_path_uses_adapter_type_registry():
    source = (
        ROOT
        / "app"
        / "services"
        / "payment_webhook_service.py"
    ).read_text()

    assert "create_adapter_for_provider" in source
    assert "provider.adapter_type" in source


def test_webhook_path_uses_secret_resolver_abstraction():
    source = (
        ROOT
        / "app"
        / "services"
        / "payment_webhook_service.py"
    ).read_text()

    assert "resolve_secret(" in source
    assert "os.environ" not in source


def test_api_has_independent_forensic_writer():
    source = (
        ROOT
        / "app"
        / "api"
        / "v1"
        / "payment_provider.py"
    ).read_text()

    assert (
        "persist_forensic_record_independent"
        in source
    )
    assert "WebhookOutcomeCode" in source


def test_reliability_model_registered():
    source = (
        ROOT
        / "app"
        / "db"
        / "database.py"
    ).read_text()

    assert (
        "app.models.payment_reliability"
        in source
    )


def test_no_provider_specific_direct_balance_mutation():
    paths = list(
        (
            ROOT
            / "app"
            / "services"
        ).glob("payment_*.py")
    )

    source = "\n".join(
        p.read_text()
        for p in paths
    )

    assert "balance_minor +=" not in source
    assert "balance_minor -=" not in source


def test_no_provider_specific_direct_ledger_sql():
    paths = list(
        (
            ROOT
            / "app"
            / "services"
        ).glob("payment_*.py")
    )

    source = "\n".join(
        p.read_text().lower()
        for p in paths
    )

    forbidden = (
        "insert into ledger_entries",
        "insert into ledger_transactions",
        "update ledger_entries",
        "update ledger_transactions",
        "delete from ledger_entries",
        "delete from ledger_transactions",
    )

    for expression in forbidden:
        assert expression not in source
