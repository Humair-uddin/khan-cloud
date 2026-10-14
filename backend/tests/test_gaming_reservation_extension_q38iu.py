from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.finance import (
    CustomerWallet,
    FinancialAccount,
    LedgerEntry,
    LedgerTransaction,
)
from app.models.node import Node
from app.services import gaming_billing_service, wallet_service


MINIMUM_RESERVATION = 585
PER_MINUTE = 117


class _ScalarRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FinanceDb:
    def __init__(self, *, available_minor=10_000):
        self.available_account = SimpleNamespace(
            id=uuid4(), currency="PKR"
        )
        self.reserved_account = SimpleNamespace(
            id=uuid4(), currency="PKR"
        )
        self.wallet = SimpleNamespace(
            id=uuid4(),
            currency="PKR",
            available_account_id=self.available_account.id,
            reserved_account_id=self.reserved_account.id,
        )
        self.available_minor = available_minor
        self.reserved_minor = 0
        self.transactions = {}
        self.entries = {}
        self.flush_count = 0
        self.nodes = {}


    @staticmethod
    def _entity(statement):
        return statement.column_descriptions[0].get("entity")

    @staticmethod
    def _parameter(statement, prefix):
        for name, value in statement.compile().params.items():
            if name.startswith(prefix):
                return value
        raise AssertionError(
            f"Missing {prefix!r} parameter in {statement!s}"
        )

    def scalar(self, statement):
        entity = self._entity(statement)
        if entity is LedgerTransaction:
            key = self._parameter(statement, "idempotency_key")
            return self.transactions.get(key)
        if entity is CustomerWallet:
            return self.wallet
        raise AssertionError(f"Unexpected scalar entity: {entity!r}")

    def scalars(self, statement):
        entity = self._entity(statement)
        if entity is LedgerEntry:
            transaction_id = self._parameter(
                statement, "transaction_id"
            )
            return _ScalarRows(self.entries.get(transaction_id, []))
        raise AssertionError(f"Unexpected scalars entity: {entity!r}")

    def get(self, model, object_id):
        if model is Node and object_id in self.nodes:
            return self.nodes[object_id]

        if model is CustomerWallet and object_id == self.wallet.id:
            return self.wallet
        if model is FinancialAccount:
            if object_id == self.available_account.id:
                return self.available_account
            if object_id == self.reserved_account.id:
                return self.reserved_account
        raise AssertionError(
            f"Unexpected get: model={model!r}, id={object_id!r}"
        )

    def flush(self):
        self.flush_count += 1


def _reservation(*, reservation_id=None, consumed_minor=0):
    return SimpleNamespace(
        id=reservation_id or uuid4(),
        wallet_id=None,
        currency="PKR",
        reserved_minor=MINIMUM_RESERVATION,
        consumed_minor=consumed_minor,
        released_minor=0,
        status="reserved",
    )


def _install_fake_ledger(monkeypatch, db):
    def balances(current_db, _wallet):
        assert current_db is db
        return {
            "available_minor": db.available_minor,
            "reserved_minor": db.reserved_minor,
        }

    def post_transaction(
        current_db,
        *,
        transaction_type,
        currency,
        idempotency_key,
        lines,
        external_reference="",
        **_kwargs,
    ):
        assert current_db is db
        existing = db.transactions.get(idempotency_key)
        if existing is not None:
            return existing

        transaction = SimpleNamespace(
            id=uuid4(),
            transaction_type=transaction_type,
            currency=currency,
            idempotency_key=idempotency_key,
            external_reference=external_reference,
            status="posted",
        )
        entries = [
            SimpleNamespace(
                transaction_id=transaction.id,
                account_id=line.account.id,
                side=line.side,
                amount_minor=line.amount_minor,
                memo=line.memo,
            )
            for line in lines
        ]
        db.transactions[idempotency_key] = transaction
        db.entries[transaction.id] = entries

        amount_minor = entries[0].amount_minor
        db.available_minor -= amount_minor
        db.reserved_minor += amount_minor
        return transaction

    monkeypatch.setattr(wallet_service, "wallet_balances", balances)
    monkeypatch.setattr(wallet_service, "post_transaction", post_transaction)


def _extension_key(session_id, reservation, target=702):
    return gaming_billing_service._gaming_reservation_extension_idempotency_key(
        session_id=session_id,
        reservation_id=reservation.id,
        target_reserved_minor=target,
    )


def test_same_reservation_same_target_retry_is_idempotent(monkeypatch):
    db = _FinanceDb()
    reservation = _reservation()
    reservation.wallet_id = db.wallet.id
    key = _extension_key(uuid4(), reservation)
    _install_fake_ledger(monkeypatch, db)

    first = wallet_service.extend_reservation(
        db,
        reservation=reservation,
        amount_minor=PER_MINUTE,
        idempotency_key=key,
    )
    available_after_first = db.available_minor
    second = wallet_service.extend_reservation(
        db,
        reservation=reservation,
        amount_minor=PER_MINUTE,
        idempotency_key=key,
    )

    assert second is first
    assert reservation.reserved_minor == 702
    assert db.available_minor == available_after_first
    assert db.reserved_minor == PER_MINUTE
    assert len(db.transactions) == 1
    assert len(db.entries[first.id]) == 2


def test_same_session_different_reservations_same_target_do_not_collide(
    monkeypatch,
):
    db = _FinanceDb()
    session_id = uuid4()
    first_reservation = _reservation()
    second_reservation = _reservation()
    first_reservation.wallet_id = db.wallet.id
    second_reservation.wallet_id = db.wallet.id
    first_key = _extension_key(session_id, first_reservation)
    second_key = _extension_key(session_id, second_reservation)
    _install_fake_ledger(monkeypatch, db)

    first = wallet_service.extend_reservation(
        db,
        reservation=first_reservation,
        amount_minor=PER_MINUTE,
        idempotency_key=first_key,
    )
    second = wallet_service.extend_reservation(
        db,
        reservation=second_reservation,
        amount_minor=PER_MINUTE,
        idempotency_key=second_key,
    )

    assert first_key != second_key
    assert str(first_reservation.id) in first_key
    assert str(second_reservation.id) in second_key
    assert first is not second
    assert first_reservation.reserved_minor == 702
    assert second_reservation.reserved_minor == 702
    assert db.available_minor == 10_000 - (2 * PER_MINUTE)
    assert db.reserved_minor == 2 * PER_MINUTE
    assert len(db.transactions) == 2


def test_foreign_reservation_extension_replay_fails_closed(monkeypatch):
    db = _FinanceDb()
    first_reservation = _reservation()
    second_reservation = _reservation()
    first_reservation.wallet_id = db.wallet.id
    second_reservation.wallet_id = db.wallet.id
    reused_key = "synthetic-extension-replay"
    _install_fake_ledger(monkeypatch, db)

    wallet_service.extend_reservation(
        db,
        reservation=first_reservation,
        amount_minor=PER_MINUTE,
        idempotency_key=reused_key,
    )

    with pytest.raises(
        wallet_service.WalletError,
        match="reused with different contents",
    ):
        wallet_service.extend_reservation(
            db,
            reservation=second_reservation,
            amount_minor=PER_MINUTE,
            idempotency_key=reused_key,
        )

    assert second_reservation.reserved_minor == MINIMUM_RESERVATION
    assert len(db.transactions) == 1


def test_y3_shaped_historical_v1_collision_no_longer_exhausts(
    monkeypatch,
):
    db = _FinanceDb(available_minor=100_000)
    session_id = uuid4()
    prior_reservation_id = uuid4()
    reservation = _reservation()
    reservation.wallet_id = db.wallet.id

    for target in (702, 819, 936, 1053, 1170):
        key = f"gaming:{session_id}:extend:{target}:v1"
        transaction = SimpleNamespace(
            id=uuid4(),
            transaction_type="wallet_reservation_extension",
            currency="PKR",
            idempotency_key=key,
            external_reference=str(prior_reservation_id),
            status="posted",
        )
        db.transactions[key] = transaction
        db.entries[transaction.id] = [
            SimpleNamespace(amount_minor=PER_MINUTE),
            SimpleNamespace(amount_minor=PER_MINUTE),
        ]

    started_at = datetime(2026, 9, 10, 21, 12, tzinfo=UTC)
    session = SimpleNamespace(
        id=session_id,
        product_sku_id=uuid4(),
        usage_reservation_id=reservation.id,
        status="running",
        started_at=started_at,
        last_metered_at=started_at,
        per_minute_price_minor=PER_MINUTE,
        host_payout_per_minute_minor=0,
        node_id=uuid4(),
        desired_state="running",
        billing_stop_reason="",
        availability_cutoff_at=None,
    )

    _install_fake_ledger(monkeypatch, db)
    monkeypatch.setattr(
        gaming_billing_service,
        "_reservation_for_update",
        lambda current_db, current_session: reservation,
    )
    monkeypatch.setattr(
        gaming_billing_service,
        "wallet_balances",
        lambda current_db, wallet: {
            "available_minor": db.available_minor,
            "reserved_minor": db.reserved_minor,
        },
    )

    def consume_platform_usage(
        current_db,
        *,
        reservation,
        gross_charge_minor,
        **_kwargs,
    ):
        assert current_db is db
        reservation.consumed_minor += gross_charge_minor
        if (
            reservation.consumed_minor + reservation.released_minor
            == reservation.reserved_minor
        ):
            reservation.status = "closed"

    monkeypatch.setattr(
        gaming_billing_service,
        "consume_reserved_platform_usage",
        consume_platform_usage,
    )

    db.nodes[session.node_id] = SimpleNamespace(
        last_seen_at=started_at + timedelta(minutes=10),
        gaming_admission_auto_blocked=False,
    )

    for minute in range(1, 6):
        units = gaming_billing_service.meter_gaming_session(
            db,
            session=session,
            now=started_at + timedelta(minutes=minute),
        )
        assert units == 1
        assert session.desired_state == "running"

    new_v2_transactions = [
        key
        for key in db.transactions
        if key.startswith(
            f"gaming:{session_id}:reservation:{reservation.id}:extend:"
        )
        and key.endswith(":v2")
    ]
    assert len(new_v2_transactions) == 5
    assert reservation.consumed_minor == MINIMUM_RESERVATION
    assert reservation.reserved_minor == 1170
    assert reservation.status == "reserved"
    assert (
        reservation.reserved_minor
        - reservation.consumed_minor
        - reservation.released_minor
        == MINIMUM_RESERVATION
    )
    assert session.billing_stop_reason == ""


def test_committed_v1_extension_advances_to_next_v2_target(monkeypatch):
    db = _FinanceDb()
    session_id = uuid4()
    reservation = _reservation(consumed_minor=2 * PER_MINUTE)
    reservation.wallet_id = db.wallet.id
    reservation.reserved_minor = 702
    v1_key = f"gaming:{session_id}:extend:702:v1"
    v1_transaction = SimpleNamespace(
        id=uuid4(),
        transaction_type="wallet_reservation_extension",
        currency="PKR",
        idempotency_key=v1_key,
        external_reference=str(reservation.id),
        status="posted",
    )
    db.transactions[v1_key] = v1_transaction
    db.entries[v1_transaction.id] = [
        SimpleNamespace(amount_minor=PER_MINUTE),
        SimpleNamespace(amount_minor=PER_MINUTE),
    ]
    session = SimpleNamespace(
        id=session_id,
        per_minute_price_minor=PER_MINUTE,
        desired_state="running",
        billing_stop_reason="",
    )

    _install_fake_ledger(monkeypatch, db)
    monkeypatch.setattr(
        gaming_billing_service,
        "_reservation_for_update",
        lambda current_db, current_session: reservation,
    )
    monkeypatch.setattr(
        gaming_billing_service,
        "wallet_balances",
        lambda current_db, wallet: {
            "available_minor": db.available_minor,
            "reserved_minor": db.reserved_minor,
        },
    )

    gaming_billing_service.ensure_runtime_coverage(db, session=session)

    v2_key = _extension_key(session_id, reservation, target=819)
    assert v1_key in db.transactions
    assert v2_key in db.transactions
    assert reservation.reserved_minor == 819
    assert session.desired_state == "running"


def test_insufficient_funds_still_requests_stop(monkeypatch):
    db = _FinanceDb(available_minor=0)
    reservation = _reservation(consumed_minor=PER_MINUTE)
    reservation.wallet_id = db.wallet.id
    session = SimpleNamespace(
        id=uuid4(),
        per_minute_price_minor=PER_MINUTE,
        desired_state="running",
        billing_stop_reason="",
    )

    monkeypatch.setattr(
        gaming_billing_service,
        "_reservation_for_update",
        lambda current_db, current_session: reservation,
    )
    monkeypatch.setattr(
        gaming_billing_service,
        "wallet_balances",
        lambda current_db, wallet: {
            "available_minor": 0,
            "reserved_minor": 0,
        },
    )
    monkeypatch.setattr(
        gaming_billing_service,
        "extend_reservation",
        lambda *_args, **_kwargs: pytest.fail(
            "insufficient funds must not post an extension"
        ),
    )

    result = gaming_billing_service.ensure_runtime_coverage(
        db, session=session
    )

    assert result is reservation
    assert session.desired_state == "stopped"
    assert session.billing_stop_reason == "insufficient_wallet_balance"
    assert reservation.reserved_minor == MINIMUM_RESERVATION
