from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.cli import reconcile_gateway


class FakeDB:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_cli_success(monkeypatch, capsys):
    db = FakeDB()

    monkeypatch.setattr(
        reconcile_gateway,
        "SessionLocal",
        lambda: db,
    )

    mapping_id = uuid4()

    monkeypatch.setattr(
        reconcile_gateway,
        "reconcile_gateway_batch",
        lambda db, limit: SimpleNamespace(
            selected=1,
            succeeded=1,
            failed=0,
            mapping_ids=(mapping_id,),
        ),
    )

    rc = reconcile_gateway.main(
        ["--limit", "25"]
    )

    captured = capsys.readouterr()

    assert rc == 0
    assert "selected=1" in captured.out
    assert "succeeded=1" in captured.out
    assert "failed=0" in captured.out
    assert str(mapping_id) in captured.out
    assert db.closed is True


def test_cli_partial_failure_returns_two(
    monkeypatch,
    capsys,
):
    db = FakeDB()

    monkeypatch.setattr(
        reconcile_gateway,
        "SessionLocal",
        lambda: db,
    )

    monkeypatch.setattr(
        reconcile_gateway,
        "reconcile_gateway_batch",
        lambda db, limit: SimpleNamespace(
            selected=3,
            succeeded=2,
            failed=1,
            mapping_ids=(),
        ),
    )

    rc = reconcile_gateway.main([])

    captured = capsys.readouterr()

    assert rc == 2
    assert "failed=1" in captured.out
    assert db.closed is True


def test_cli_orchestration_error_returns_one(
    monkeypatch,
    capsys,
):
    db = FakeDB()

    monkeypatch.setattr(
        reconcile_gateway,
        "SessionLocal",
        lambda: db,
    )

    def fail(db, limit):
        raise reconcile_gateway.GatewayOrchestrationError(
            "live disabled"
        )

    monkeypatch.setattr(
        reconcile_gateway,
        "reconcile_gateway_batch",
        fail,
    )

    rc = reconcile_gateway.main([])

    captured = capsys.readouterr()

    assert rc == 1
    assert "live disabled" in captured.err
    assert db.closed is True


def test_cli_invalid_limit_returns_one(
    monkeypatch,
    capsys,
):
    db = FakeDB()

    monkeypatch.setattr(
        reconcile_gateway,
        "SessionLocal",
        lambda: db,
    )

    def fail(db, limit):
        raise ValueError(
            "limit must be at least 1."
        )

    monkeypatch.setattr(
        reconcile_gateway,
        "reconcile_gateway_batch",
        fail,
    )

    rc = reconcile_gateway.main(
        ["--limit", "0"]
    )

    captured = capsys.readouterr()

    assert rc == 1
    assert "limit must be at least 1" in captured.err
    assert db.closed is True
