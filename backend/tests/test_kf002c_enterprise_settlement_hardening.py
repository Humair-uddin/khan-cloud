from pathlib import Path

from app.models.financial_obligation import (
    CustomerFinancialObligation,
)
from app.models.payment_provider import (
    PaymentProviderReference,
)
from app.schemas.payment_provider import (
    NormalizedPaymentEvent,
)
from app.services.rbac_service import DEFAULT_ROLES


def test_financial_obligation_model_contract():
    columns = {
        column.name
        for column
        in CustomerFinancialObligation.__table__.columns
    }

    assert {
        "organization_id",
        "user_id",
        "wallet_id",
        "chargeback_dispute_id",
        "receivable_account_id",
        "provider",
        "provider_reference",
        "currency",
        "original_amount_minor",
        "outstanding_amount_minor",
        "status",
    } <= columns


def test_financial_obligation_provider_identity_unique():
    constraints = {
        constraint.name
        for constraint
        in CustomerFinancialObligation.__table__.constraints
    }

    assert (
        "uq_customer_obligation_provider_reference"
        in constraints
    )


def test_provider_reference_unique_external_identity():
    constraints = {
        constraint.name
        for constraint
        in PaymentProviderReference.__table__.constraints
    }

    assert (
        "uq_payment_provider_external_reference"
        in constraints
    )


def test_refund_processing_event_is_normalized():
    event = NormalizedPaymentEvent(
        provider="fake",
        event_id="evt-refund-processing",
        event_type="refund.processing",
        provider_timestamp=1000,
    )

    assert event.event_type == "refund.processing"


def test_dedicated_finance_roles_exist():
    assert "finance_admin" in DEFAULT_ROLES
    assert "finance_operator" in DEFAULT_ROLES

    admin = DEFAULT_ROLES["finance_admin"]
    operator = DEFAULT_ROLES["finance_operator"]

    assert "finance.ledger.manage" in admin
    assert "finance.fx.manage" in admin
    assert "finance.payment_providers.manage" in admin

    assert "finance.deposits.manage" in operator
    assert "finance.payouts.manage" in operator
    assert "finance.reconciliation.manage" in operator

    assert "finance.ledger.manage" not in operator
    assert "finance.fx.manage" not in operator
    assert (
        "finance.payment_providers.manage"
        not in operator
    )


def test_generic_operator_loses_high_risk_finance():
    operator = DEFAULT_ROLES["operator"]

    assert "finance.read" in operator

    assert (
        "finance.deposits.manage"
        not in operator
    )
    assert (
        "finance.reconciliation.manage"
        not in operator
    )
    assert (
        "finance.ledger.manage"
        not in operator
    )
    assert (
        "finance.payouts.manage"
        not in operator
    )
    assert (
        "finance.fx.manage"
        not in operator
    )


def test_refund_service_has_real_completion_accounting():
    source = Path(
        "app/services/refund_service.py"
    ).read_text()

    assert "def mark_refund_processing(" in source
    assert "def mark_refund_paid(" in source
    assert "def mark_refund_failed(" in source

    assert 'transaction_type="customer_refund_paid"' in source
    assert "reverse_transaction(" in source
    assert '"customer_receivable"' in source
    assert "CustomerFinancialObligation(" in source


def test_payout_callbacks_are_replay_safe():
    source = Path(
        "app/services/payout_service.py"
    ).read_text()

    assert 'if payout.status == "paid":' in source
    assert 'if payout.status == "failed":' in source

    assert (
        "replayed with "
        '"a different provider reference."'
        in source
        or
        "a different provider reference"
        in source
    )


def test_event_processor_uses_provider_reference_mapping():
    source = Path(
        "app/services/payment_event_processor.py"
    ).read_text()

    assert "bind_provider_reference(" in source
    assert 'reference_type="deposit"' in source
    assert 'reference_type="refund"' in source
    assert 'reference_type="payout"' in source
    assert 'reference_type="chargeback"' in source
    assert (
        'reference_type="treasury_settlement"'
        in source
    )


def test_event_processor_audits_provider_transitions():
    source = Path(
        "app/services/payment_event_processor.py"
    ).read_text()

    assert "record_audit_event(" in source
    assert '"finance.refund.paid"' in source
    assert '"finance.refund.failed"' in source
    assert '"finance.payout.paid"' in source
    assert '"finance.payout.failed"' in source
    assert '"finance.chargeback.post"' in source


def test_chargeback_insufficient_wallet_is_not_rejected():
    source = Path(
        "app/services/refund_service.py"
    ).read_text()

    assert (
        "Customer wallet cannot absorb this chargeback."
        not in source
    )

    assert "wallet_absorption" in source
    assert "receivable_amount" in source


def test_hardening_migration_descends_from_kf002_foundation():
    migration = Path(
        "migrations/versions/"
        "f2a002c10001_"
        "enterprise_settlement_hardening_v1.py"
    ).read_text()

    assert 'revision = "f2a002c10001"' in migration
    assert 'down_revision = "f2a002b10002"' in migration

    assert (
        '"customer_financial_obligations"'
        in migration
    )

    assert 'server_default=sa.text("now()")' in migration


def test_payment_services_do_not_directly_mutate_ledger_sql():
    paths = [
        Path("app/services/refund_service.py"),
        Path("app/services/payout_service.py"),
        Path("app/services/payment_event_processor.py"),
        Path(
            "app/services/"
            "payment_provider_reference_service.py"
        ),
    ]

    combined = "\n".join(
        path.read_text()
        for path in paths
    )

    assert "UPDATE ledger_entries" not in combined
    assert "DELETE FROM ledger_entries" not in combined
    assert "INSERT INTO ledger_entries" not in combined

    assert "UPDATE ledger_transactions" not in combined
    assert "DELETE FROM ledger_transactions" not in combined
    assert "INSERT INTO ledger_transactions" not in combined


def test_provider_reference_metadata_is_resource_stable():
    source = Path(
        "app/services/payment_event_processor.py"
    ).read_text()

    start = source.index("def _bind_reference(")
    end = source.index(
        "\ndef process_normalized_event(",
        start,
    )

    helper = source[start:end]

    assert '"event_id": event.event_id' not in helper
    assert '"event_type": event.event_type' not in helper
    assert '"provider": event.provider' in helper
