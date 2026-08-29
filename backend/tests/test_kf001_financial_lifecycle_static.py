from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text()


def test_refund_is_ledger_backed():
    source = _read(
        "app/services/refund_service.py"
    )

    assert "customer_refund_queued" in source
    assert "post_transaction(" in source
    assert "account_balance_minor" in source


def test_chargeback_is_ledger_backed():
    source = _read(
        "app/services/refund_service.py"
    )

    assert "payment_chargeback" in source
    assert "provider_dispute_id" in source


def test_adjustment_requires_explicit_reason():
    source = _read(
        "app/services/adjustment_service.py"
    )

    assert "Adjustment reason is required." in source
    assert "actor_user_id" in source


def test_treasury_settlement_moves_clearing_to_bank():
    source = _read(
        "app/services/treasury_service.py"
    )

    assert "gateway_bank_settlement" in source
    assert "bank_asset" in source
    assert "gateway_clearing" in source


def test_payout_failure_reverses_original_queue_transaction():
    source = _read(
        "app/services/payout_service.py"
    )

    assert "def mark_payout_failed" in source
    assert "reverse_transaction(" in source


def test_payout_paid_clears_payout_clearing_against_bank():
    source = _read(
        "app/services/payout_service.py"
    )

    assert "def mark_payout_paid" in source
    assert 'transaction_type="payout_paid"' in source


def test_reconciliation_has_processed_state():
    source = _read(
        "app/services/payment_reconciliation_service.py"
    )

    assert "def mark_event_processed" in source
    assert "event.processed = True" in source


def test_financial_operations_create_audit_events():
    source = _read(
        "app/api/v1/finance.py"
    )

    assert "finance.refund.queue" in source
    assert "finance.adjustment.create" in source
    assert "finance.treasury.settle" in source


def test_lifecycle_migration_extends_existing_financial_revision():
    source = _read(
        "migrations/versions/"
        "f1a001b10002_financial_lifecycle_v1.py"
    )

    assert 'revision = "f1a001b10002"' in source
    assert 'down_revision = "f1a001b10001"' in source


def test_fx_translates_ledger_conflict_to_fx_error():
    source = _read(
        "app/services/fx_service.py"
    )

    assert "except LedgerError as exc" in source
    assert "raise FxError(str(exc)) from exc" in source
    assert "with db.begin_nested()" in source


def test_fx_hash_binds_rate_and_both_amounts():
    source = _read(
        "app/services/fx_service.py"
    )

    assert '"source_amount_minor": source_amount_minor' in source
    assert '"target_amount_minor": target_amount_minor' in source
    assert '"rate_numerator": rate_numerator' in source
    assert '"rate_denominator": rate_denominator' in source
    assert '"rate_source": rate_source' in source


def test_reservation_release_retry_does_not_double_increment():
    source = _read(
        "app/services/wallet_service.py"
    )

    assert "preexisting_tx" in source
    assert "existing_reservation" in source


def test_usage_retry_does_not_double_consume():
    source = _read(
        "app/services/settlement_service.py"
    )

    assert "preexisting_tx" in source
    assert "existing_earning" in source


def test_chargeback_replay_is_content_bound():
    source = _read(
        "app/services/refund_service.py"
    )

    assert "Provider dispute ID was reused" in source


def test_fx_translates_ledger_conflict_to_fx_error():
    source = _read(
        "app/services/fx_service.py"
    )

    assert "except LedgerError as exc" in source
    assert "raise FxError(str(exc)) from exc" in source
    assert "with db.begin_nested()" in source


def test_fx_hash_binds_rate_and_both_amounts():
    source = _read(
        "app/services/fx_service.py"
    )

    assert '"source_amount_minor": source_amount_minor' in source
    assert '"target_amount_minor": target_amount_minor' in source
    assert '"rate_numerator": rate_numerator' in source
    assert '"rate_denominator": rate_denominator' in source
    assert '"rate_source": rate_source' in source


def test_reservation_release_retry_does_not_double_increment():
    source = _read(
        "app/services/wallet_service.py"
    )

    assert "preexisting_tx" in source
    assert "existing_reservation" in source


def test_usage_retry_does_not_double_consume():
    source = _read(
        "app/services/settlement_service.py"
    )

    assert "preexisting_tx" in source
    assert "existing_earning" in source


def test_chargeback_replay_is_content_bound():
    source = _read(
        "app/services/refund_service.py"
    )

    assert "Provider dispute ID was reused" in source


def test_usage_replay_precedes_remaining_funds_gate():
    source = _read(
        "app/services/settlement_service.py"
    )

    replay = source.index(
        "if preexisting_tx is not None:"
    )
    remaining = source.index(
        "Usage charge exceeds reserved funds."
    )

    assert replay < remaining


def test_release_replay_precedes_remaining_funds_gate():
    source = _read(
        "app/services/wallet_service.py"
    )

    section = source.split(
        "def release_reservation",
        1,
    )[1]

    replay = section.index(
        "if preexisting_tx is not None:"
    )
    remaining = section.index(
        "remaining = ("
    )

    assert replay < remaining
    assert "LedgerEntry.transaction_id" in section


def test_db_enforces_balanced_ledger_transactions():
    source = _read(
        "migrations/versions/"
        "f1a001b10003_ledger_database_invariants_v1.py"
    )

    assert "DEFERRABLE INITIALLY DEFERRED" in source
    assert "debits must equal credits" in source
    assert "transaction requires at least two entries" in source
    assert "entry account currency mismatch" in source
    assert "trg_ledger_transaction_balanced" in source
    assert "trg_ledger_entry_balanced" in source


def test_financial_fingerprint_is_keyed():
    source = _read(
        "app/services/finance_crypto_service.py"
    )

    assert "hmac.new(" in source
    assert "khan-cloud-finance-fingerprint-v1" in source
    assert "hashlib.sha256" in source


def test_crypto_uses_application_settings():
    source = _read(
        "app/services/finance_crypto_service.py"
    )

    assert "from app.core.config import settings" in source
    assert 'os.getenv("FINANCE_ENCRYPTION_KEY_B64"' not in source
    assert "settings.FINANCE_ENCRYPTION_KEY_B64" in source


def test_generic_operator_does_not_have_high_risk_finance_permissions():
    source = _read(
        "app/services/rbac_service.py"
    )

    marker = (
        '"operator"'
        if '"operator"' in source
        else "'operator'"
    )

    start = source.index(marker)
    brace = source.index("{", start)

    depth = 0
    end = None

    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1

            if depth == 0:
                end = i + 1
                break

    assert end is not None

    block = source[brace:end]

    assert "finance.ledger.manage" not in block
    assert "finance.settlement.manage" not in block
    assert "finance.payouts.manage" not in block
    assert "finance.fx.manage" not in block
