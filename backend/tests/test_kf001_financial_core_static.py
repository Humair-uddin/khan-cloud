from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text()


def test_legacy_wallet_no_longer_directly_increments_balance():
    source = _read(
        "app/services/commercial_service.py"
    )
    assert "w.balance_minor+=" not in source
    assert "ledger_authoritative_topup" in source


def test_financial_account_has_no_balance_authority_column():
    source = _read(
        "app/models/finance.py"
    )
    financial_account_section = source.split(
        "class FinancialAccount"
    )[1].split(
        "class LedgerTransaction"
    )[0]

    assert "balance_minor" not in financial_account_section


def test_ledger_enforces_positive_entries():
    migration = _read(
        "migrations/versions/"
        "f1a001b10001_financial_core_v1.py"
    )
    assert "amount_minor > 0" in migration


def test_finance_supports_pkr_and_usd():
    source = _read(
        "app/models/finance.py"
    )
    assert '("PKR", "USD")' in source


def test_post_transaction_rejects_cross_currency_lines():
    source = _read(
        "app/services/ledger_service.py"
    )
    assert "Cross-currency entries are forbidden" in source


def test_finance_has_explicit_fx_bridge():
    source = _read(
        "app/services/fx_service.py"
    )
    assert "fx_bridge" in source
    assert "source_currency == target_currency" in source


def test_payout_destination_is_encrypted_not_plain_account_number():
    source = _read(
        "app/models/finance.py"
    )
    assert "encrypted_payload" in source
    assert "encryption_key_version" in source


def test_one_preferred_payout_destination_is_database_enforced():
    migration = _read(
        "migrations/versions/"
        "f1a001b10001_financial_core_v1.py"
    )
    assert "uq_payout_methods_one_preferred_host" in migration
    assert "is_preferred = true AND status = 'active'" in migration


def test_gateway_event_replay_contract_exists():
    source = _read(
        "app/services/payment_reconciliation_service.py"
    )
    assert "replayed with different contents" in source
    assert "hmac.compare_digest" in source


def test_finance_rbac_is_separate_from_commerce():
    source = _read(
        "app/services/rbac_service.py"
    )
    assert '"finance.read"' in source
    assert '"finance.payouts.manage"' in source
    assert '"finance.fx.manage"' in source


def test_posted_ledger_has_database_immutability_triggers():
    migration = _read(
        "migrations/versions/"
        "f1a001b10001_financial_core_v1.py"
    )

    assert "trg_ledger_entries_immutable" in migration
    assert "trg_ledger_transactions_immutable" in migration
    assert "UPDATE/DELETE is forbidden" in migration


def test_reversal_does_not_mutate_original_transaction():
    source = _read(
        "app/services/ledger_service.py"
    )

    assert 'original.status = "reversed"' not in source
    assert "reversal.reversed_transaction_id = original.id" not in source
    assert "reversed_transaction_id=original.id" in source


def test_idempotency_conflict_is_detected():
    source = _read(
        "app/services/ledger_service.py"
    )

    assert "request_hash" in source
    assert (
        "Idempotency key was reused with different"
        in source
    )
