from pathlib import Path

from app.models.payment_provider import (
    PaymentProvider,
    PaymentProviderReference,
    PaymentWebhookReceipt,
)


def test_provider_credentials_are_references_not_secret_values():
    columns = {
        c.name
        for c in PaymentProvider.__table__.columns
    }

    assert "credential_reference" in columns
    assert "webhook_secret_reference" in columns

    assert "credential" not in columns
    assert "webhook_secret" not in columns


def test_webhook_receipt_has_content_binding():
    columns = {
        c.name
        for c in PaymentWebhookReceipt.__table__.columns
    }

    assert "raw_body_sha256" in columns
    assert "normalized_payload_sha256" in columns
    assert "provider_timestamp" in columns
    assert "signature_verified" in columns


def test_provider_reference_mapping_is_unique_by_external_identity():
    constraints = {
        c.name
        for c in PaymentProviderReference.__table__.constraints
    }

    assert "uq_payment_provider_external_reference" in constraints


def test_provider_cannot_directly_mutate_wallet_or_ledger():
    files = [
        Path("app/services/payment_provider_service.py"),
        Path("app/services/payment_provider_registry.py"),
        Path("app/services/payment_webhook_service.py"),
        Path("app/services/payment_event_processor.py"),
    ]

    combined = "\n".join(
        path.read_text()
        for path in files
    )

    assert "balance_minor +=" not in combined
    assert "UPDATE ledger_entries" not in combined
    assert "UPDATE ledger_transactions" not in combined
    assert "INSERT INTO ledger_entries" not in combined


def test_payment_provider_configuration_not_granted_to_operator():
    source = Path(
        "app/services/rbac_service.py"
    ).read_text()

    marker = (
        '"operator"'
        if '"operator"' in source
        else "'operator'"
    )

    start = source.index(marker)
    brace = source.index("{", start)

    depth = 0
    end = None

    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    assert end is not None

    operator = source[brace:end]

    assert (
        "finance.payment_providers.manage"
        not in operator
    )


def test_migration_descends_from_financial_core():
    migration = Path(
        "migrations/versions/"
        "f2a002b10001_payment_provider_adapter_v1.py"
    ).read_text()

    assert 'revision = "f2a002b10001"' in migration
    assert 'down_revision = "f1a001b10003"' in migration


def test_payment_provider_migrations_supply_base_timestamp_defaults():
    from pathlib import Path

    migration = Path(
        "migrations/versions/"
        "f2a002b10002_payment_provider_timestamp_defaults_v1.py"
    ).read_text()

    assert 'revision = "f2a002b10002"' in migration
    assert 'down_revision = "f2a002b10001"' in migration

    assert '"payment_providers"' in migration
    assert '"payment_provider_references"' in migration
    assert '"payment_webhook_receipts"' in migration

    assert '"created_at"' in migration
    assert '"updated_at"' in migration
    assert 'sa.text("now()")' in migration
