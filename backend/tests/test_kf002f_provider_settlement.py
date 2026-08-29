from pathlib import Path

from app.models.finance import (
    PaymentReconciliationEvent,
)
from app.models.payment_settlement import (
    PaymentProviderSettlementBatch,
    PaymentProviderSettlementItem,
)
from app.services.payment_adapter_registry import (
    ProviderSettlementBatchResult,
    ProviderSettlementItemResult,
)


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (
        ROOT / path
    ).read_text()


def test_settlement_models_use_existing_base_model_contract():
    assert (
        PaymentProviderSettlementBatch.__tablename__
        == "payment_provider_settlement_batches"
    )
    assert (
        PaymentProviderSettlementItem.__tablename__
        == "payment_provider_settlement_items"
    )

    batch_columns = {
        c.name
        for c in PaymentProviderSettlementBatch.__table__.columns
    }

    item_columns = {
        c.name
        for c in PaymentProviderSettlementItem.__table__.columns
    }

    assert {
        "provider_id",
        "provider_code",
        "provider_settlement_reference",
        "settlement_currency",
        "gross_amount_minor",
        "fee_amount_minor",
        "net_amount_minor",
        "content_hash",
        "idempotency_key",
        "credential_reference_snapshot",
    } <= batch_columns

    assert {
        "settlement_batch_id",
        "provider_line_id",
        "provider_transaction_reference",
        "presentment_currency",
        "settlement_currency",
        "gross_amount_minor",
        "fee_amount_minor",
        "net_amount_minor",
        "explicit_fx_transaction_id",
        "reconciliation_status",
        "reconciliation_event_id",
    } <= item_columns


def test_existing_reconciliation_model_extended():
    columns = {
        c.name
        for c in PaymentReconciliationEvent.__table__.columns
    }

    assert {
        "reconciliation_type",
        "outcome",
        "provider_amount_minor",
        "internal_amount_minor",
        "provider_currency",
        "internal_currency",
        "internal_resource_type",
        "internal_resource_id",
        "resolution_reason",
        "resolved_at",
    } <= columns


def test_required_reconciliation_outcomes_present():
    text = source(
        "app/services/payment_reconciliation_service.py"
    )

    for status in (
        "matched",
        "amount_mismatch",
        "currency_mismatch",
        "missing_internal",
        "missing_provider",
        "duplicate_provider",
        "pending_review",
        "resolved",
    ):
        assert status in text


def test_settlement_is_content_bound():
    text = source(
        "app/services/payment_settlement_service.py"
    )

    assert "canonical_settlement_hash" in text
    assert (
        "idempotency key was reused "
        "with different contents"
    ) in text
    assert (
        "settlement reference was replayed "
        "with different contents"
    ) in text


def test_settlement_preserves_explicit_fx_boundary():
    text = source(
        "app/services/payment_settlement_service.py"
    )

    assert "explicit_fx_transaction_id" in text
    assert (
        "explicit auditable FX transaction is required"
        in text
    )


def test_adapter_contract_is_normalized():
    text = source(
        "app/services/payment_adapter_registry.py"
    )

    assert "def capture_payment(" in text
    assert "def execute_refund(" in text
    assert "def execute_payout(" in text
    assert "def fetch_settlement_batches(" in text
    assert "def lookup_transaction(" in text
    assert "def get_balance(" in text

    assert ProviderSettlementBatchResult
    assert ProviderSettlementItemResult


def test_settlement_fetch_uses_existing_outbox():
    text = source(
        "app/services/payment_settlement_execution.py"
    )

    assert "enqueue_outbox_message(" in text
    assert 'event_type="settlement.fetch"' in text
    assert "fetch_settlement_batches" in text


def test_credential_snapshot_contains_reference_not_secret():
    text = source(
        "app/services/payment_settlement_execution.py"
    )

    assert '"credential_reference"' in text
    assert "resolve_secret(credential_reference)" in text

    outbox_block = text.split(
        "def enqueue_provider_settlement_fetch",
        1,
    )[1].split(
        "def execute_provider_settlement_fetch",
        1,
    )[0]

    assert "resolve_secret(" not in outbox_block
    assert '"credential"' not in outbox_block


def test_payout_decrypts_only_at_provider_boundary():
    execution = source(
        "app/services/payment_payout_execution.py"
    )

    outbox = source(
        "app/services/payout_service.py"
    )

    assert "decrypt_financial_payload(" in execution
    assert '"destination":' in execution
    assert (
        '"encrypted_payload": method.encrypted_payload'
        not in execution
    )

    enqueue = outbox.split(
        "def enqueue_payout_execution(",
        1,
    )[1]

    assert '"destination"' not in enqueue
    assert '"encrypted_payload"' not in enqueue


def test_payout_outbox_snapshots_external_secret_reference():
    payout = source(
        "app/services/payout_service.py"
    )

    worker = source(
        "app/services/payment_execution_worker.py"
    )

    assert '"credential_reference"' in payout
    assert "credential_reference=(" in worker


def test_reconciliation_resolution_requires_correction_reference():
    text = source(
        "app/services/payment_reconciliation_service.py"
    )

    assert "def resolve_reconciliation_event(" in text
    assert (
        "Adjustment/reversal reference is required"
        in text
    )


def test_reconciliation_never_rewrites_ledger():
    text = source(
        "app/services/payment_reconciliation_service.py"
    ).upper()

    assert "INSERT INTO LEDGER_" not in text
    assert "UPDATE LEDGER_" not in text
    assert "DELETE FROM LEDGER_" not in text


def test_settlement_never_mutates_balances():
    for path in (
        "app/services/payment_settlement_service.py",
        "app/services/payment_settlement_execution.py",
        "app/services/payment_reconciliation_service.py",
    ):
        text = source(path)

        assert "balance_minor +=" not in text
        assert "balance_minor -=" not in text


def test_migration_is_forward_only_from_kf002e():
    text = source(
        "migrations/versions/"
        "f2a002f10001_provider_settlement_reconciliation_v1.py"
    )

    assert 'revision = "f2a002f10001"' in text
    assert 'down_revision = "f2a002e10001"' in text
    assert "payment_provider_settlement_batches" in text
    assert "payment_provider_settlement_items" in text
    assert "ck_payment_reconciliation_outcome" in text


def test_existing_financial_worker_executes_settlement_fetch():
    text = source(
        "app/services/payment_execution_worker.py"
    )

    assert (
        'row.event_type == "settlement.fetch"'
        in text
    )
    assert (
        "execute_provider_settlement_fetch("
        in text
    )
    assert (
        "mark_outbox_processed("
        in text
    )
    assert (
        "schedule_outbox_retry("
        in text
    )
    assert (
        "finance.settlement.fetch"
        in text
    )


def test_kf002e_payout_worker_dispatch_contract_preserved():
    text = source(
        "app/services/payment_execution_worker.py"
    )

    assert (
        'row.event_type != "payout.execute"'
        in text
    )
    assert (
        "execute_payout_with_provider("
        in text
    )


def test_settlement_worker_uses_same_dead_letter_path():
    worker = source(
        "app/services/payment_execution_worker.py"
    )

    outbox = source(
        "app/services/payment_financial_outbox.py"
    )

    assert '"dead_letter"' in worker
    assert '"dead_letter"' in outbox
    assert "schedule_outbox_retry(" in worker


def test_four_provider_corridors_are_explicit():
    text = source("app/services/payment_provider_policy.py")
    for corridor in (
        "PK_TO_PK",
        "INTL_TO_INTL",
        "INTL_TO_PK",
        "PK_TO_INTL",
    ):
        assert corridor in text


def test_corridors_are_provider_enabled_not_globally_assumed():
    text = source("app/services/payment_provider_policy.py")
    assert "Provider does not enable payment corridor" in text
    assert "_provider_corridors" in text


def test_corridor_policy_preserves_pkr_usd_accounting():
    text = source("app/services/payment_provider_policy.py")
    assert "Pakistan-origin customer transactions must be accounted in PKR." in text
    assert "International-origin customer transactions must be accounted in USD." in text
    assert "Cross-currency settlement requires an explicit auditable FX transaction." in text


def test_settlement_operator_reuses_existing_outbox():
    text = source("app/api/v1/finance.py")
    assert '"/operator/provider-settlements/fetch"' in text
    assert "enqueue_provider_settlement_fetch" in text
    assert "payment_financial_outbox" in text


def test_reconciliation_resolution_is_operator_audited():
    text = source("app/api/v1/finance.py")
    assert '"/operator/reconciliation/{event_id}/resolve"' in text
    assert "resolve_reconciliation_event" in text
    assert '"finance.reconciliation.resolve"' in text
    assert "correction_reference" in text


def test_settlement_and_reconciliation_use_existing_rbac():
    text = source("app/api/v1/finance.py")
    assert 'require_permission("finance.reconciliation.manage")' in text
    assert 'require_permission("finance.payment_providers.manage")' in text


def test_corridor_check_is_audited():
    text = source("app/api/v1/finance.py")
    assert '"/operator/provider-policy/corridor-check"' in text
    assert '"finance.payment_provider.corridor_check"' in text


def test_f3_does_not_create_parallel_finance_router():
    backend_root = Path(__file__).resolve().parents[1]

    assert not (
        backend_root
        / "app/api/v1/payment_settlement.py"
    ).exists()

    assert not (
        backend_root
        / "app/api/v1/reconciliation.py"
    ).exists()


def test_corridor_boolean_capability_flags_are_supported():
    text = source(
        "app/services/payment_provider_policy.py"
    )

    assert '"corridor:"' in text
    assert "SUPPORTED_PAYMENT_CORRIDORS" in text


def test_reconciliation_api_uses_real_service_signature():
    text = source(
        "app/api/v1/finance.py"
    )

    assert "reason=payload.reason" in text
    assert "resolution_reason=payload.reason" not in text
    assert "previous_outcome = event.outcome" in text
    assert '"previous_outcome": previous_outcome' in text
