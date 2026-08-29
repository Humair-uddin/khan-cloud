from pathlib import Path

from app.models.financial_obligation import (
    CustomerFinancialObligation,
    CustomerObligationPayment,
)
from app.services.payment_financial_outbox import (
    FinancialOutboxError,
    build_outbox_message,
)
from app.services.payment_payout_execution import (
    PayoutExecutionResult,
)


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (
        ROOT / path
    ).read_text()


def test_obligation_payment_model_contract():
    columns = {
        c.name
        for c in CustomerObligationPayment.__table__.columns
    }

    assert {
        "obligation_id",
        "organization_id",
        "wallet_id",
        "amount_minor",
        "currency",
        "payment_type",
        "idempotency_key",
        "ledger_transaction_id",
        "external_reference",
    } <= columns


def test_obligation_projection_preserved():
    columns = {
        c.name
        for c in CustomerFinancialObligation.__table__.columns
    }

    assert "outstanding_amount_minor" in columns
    assert "status" in columns


def test_obligation_collection_is_ledger_backed():
    text = source(
        "app/services/financial_obligation_service.py"
    )

    assert (
        'transaction_type="customer_obligation_collection"'
        in text
    )
    assert "post_transaction(" in text
    assert "outstanding_amount_minor -=" in text


def test_obligation_collection_content_bound():
    text = source(
        "app/services/financial_obligation_service.py"
    )

    assert (
        "idempotency key was reused "
        "with different contents"
    ) in text


def test_cross_currency_collection_forbidden():
    text = source(
        "app/services/financial_obligation_service.py"
    )

    assert (
        "requires an explicit FX transaction"
        in text
    )


def test_chargeback_resolution_contract():
    text = source(
        "app/services/financial_obligation_service.py"
    )

    assert '"won"' in text
    assert '"lost"' in text
    assert '"reversed"' in text
    assert "chargeback_recovery" in text


def test_payout_queue_has_transactional_outbox():
    text = source(
        "app/services/payout_service.py"
    )

    assert "def enqueue_payout_execution" in text
    assert 'event_type="payout.execute"' in text
    assert "def queue_payout_for_execution" in text


def test_provider_is_not_called_from_queue_payout():
    text = source(
        "app/services/payout_service.py"
    )

    queue_body = text.split(
        "def queue_payout(",
        1,
    )[1].split(
        "def mark_payout_processing",
        1,
    )[0]

    assert "create_adapter_for_provider" not in queue_body
    assert "execute_payout" not in queue_body


def test_adapter_protocol_supports_payout_execution():
    text = source(
        "app/services/payment_adapter_registry.py"
    )

    assert "def execute_payout(" in text


def test_provider_execution_uses_adapter_type_registry():
    text = source(
        "app/services/payment_payout_execution.py"
    )

    assert "create_adapter_for_provider(" in text
    assert "enforce_provider_operation(" in text
    assert 'capability="payouts"' in text


def test_payout_execution_result_contract():
    result = PayoutExecutionResult(
        provider_reference="abc",
        status="processing",
        retryable=False,
    )

    assert result.provider_reference == "abc"
    assert result.status == "processing"


def test_execution_worker_is_outbox_driven():
    text = source(
        "app/services/payment_execution_worker.py"
    )

    assert "claim_outbox_message(" in text
    assert 'row.event_type != "payout.execute"' in text
    assert "execute_payout_with_provider(" in text
    assert "mark_outbox_processed(" in text


def test_worker_has_retry_and_dead_letter():
    worker = source(
        "app/services/payment_execution_worker.py"
    )

    outbox = source(
        "app/services/payment_financial_outbox.py"
    )

    assert "schedule_outbox_retry(" in worker
    assert '"dead_letter"' in outbox
    assert "max_attempts" in outbox


def test_payout_execution_audited():
    text = source(
        "app/services/payment_execution_worker.py"
    )

    assert "record_audit_event(" in text
    assert "finance.payout.execution" in text


def test_migration_extends_outbox_status():
    text = source(
        "migrations/versions/"
        "f2a002e10001_payout_obligation_recovery_v1.py"
    )

    assert "dead_letter" in text
    assert "customer_obligation_payments" in text
    assert "ck_customer_obligation_status" in text


def test_no_provider_balance_mutation():
    paths = [
        "app/services/payment_payout_execution.py",
        "app/services/payment_execution_worker.py",
    ]

    for path in paths:
        text = source(path)
        assert "balance_minor +=" not in text
        assert "balance_minor -=" not in text


def test_no_provider_direct_ledger_sql():
    paths = [
        "app/services/payment_payout_execution.py",
        "app/services/payment_execution_worker.py",
    ]

    for path in paths:
        text = source(path).upper()
        assert "INSERT INTO LEDGER_" not in text
        assert "UPDATE LEDGER_" not in text
        assert "DELETE FROM LEDGER_" not in text


def test_outbox_hash_remains_content_bound():
    one = build_outbox_message(
        event_type="payout.execute",
        aggregate_type="payout",
        aggregate_id="1",
        idempotency_key="same",
        payload={
            "amount_minor": 100,
            "currency": "PKR",
        },
    )

    two = build_outbox_message(
        event_type="payout.execute",
        aggregate_type="payout",
        aggregate_id="1",
        idempotency_key="same",
        payload={
            "amount_minor": 100,
            "currency": "PKR",
        },
    )

    assert one.payload_hash == two.payload_hash
