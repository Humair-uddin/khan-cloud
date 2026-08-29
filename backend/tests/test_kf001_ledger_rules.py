import pytest

from app.services.ledger_service import (
    LedgerError,
    LedgerLine,
    post_transaction,
)


class FakeAccount:
    def __init__(self, currency):
        self.currency = currency
        self.id = None


class FakeDB:
    def scalar(self, *args, **kwargs):
        return None


def test_unbalanced_transaction_rejected_before_insert():
    db = FakeDB()

    with pytest.raises(
        LedgerError,
        match="Unbalanced transaction",
    ):
        post_transaction(
            db,
            transaction_type="test",
            currency="PKR",
            idempotency_key="test-unbalanced",
            lines=[
                LedgerLine(
                    account=FakeAccount("PKR"),
                    side="debit",
                    amount_minor=100,
                ),
                LedgerLine(
                    account=FakeAccount("PKR"),
                    side="credit",
                    amount_minor=99,
                ),
            ],
        )


def test_cross_currency_transaction_rejected_before_insert():
    db = FakeDB()

    with pytest.raises(
        LedgerError,
        match="Cross-currency",
    ):
        post_transaction(
            db,
            transaction_type="test",
            currency="PKR",
            idempotency_key="test-cross-currency",
            lines=[
                LedgerLine(
                    account=FakeAccount("PKR"),
                    side="debit",
                    amount_minor=100,
                ),
                LedgerLine(
                    account=FakeAccount("USD"),
                    side="credit",
                    amount_minor=100,
                ),
            ],
        )


def test_negative_entry_rejected():
    db = FakeDB()

    with pytest.raises(
        LedgerError,
        match="positive",
    ):
        post_transaction(
            db,
            transaction_type="test",
            currency="PKR",
            idempotency_key="test-negative",
            lines=[
                LedgerLine(
                    account=FakeAccount("PKR"),
                    side="debit",
                    amount_minor=-100,
                ),
                LedgerLine(
                    account=FakeAccount("PKR"),
                    side="credit",
                    amount_minor=-100,
                ),
            ],
        )


def test_idempotency_key_is_required():
    db = FakeDB()

    with pytest.raises(
        LedgerError,
        match="Idempotency key is required",
    ):
        post_transaction(
            db,
            transaction_type="test",
            currency="PKR",
            idempotency_key="",
            lines=[
                LedgerLine(
                    account=FakeAccount("PKR"),
                    side="debit",
                    amount_minor=100,
                ),
                LedgerLine(
                    account=FakeAccount("PKR"),
                    side="credit",
                    amount_minor=100,
                ),
            ],
        )
