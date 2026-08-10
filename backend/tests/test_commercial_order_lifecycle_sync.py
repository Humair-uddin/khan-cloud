from types import SimpleNamespace
from uuid import uuid4

from app.services.compute_service import (
    _synchronize_commercial_order_for_vps_job,
)


class FakeDB:
    def __init__(self, order):
        self.order = order

    def scalar(self, statement):
        return self.order


def make_vps():
    return SimpleNamespace(id=uuid4())


def make_job(job_type, status):
    return SimpleNamespace(
        job_type=job_type,
        status=status,
    )


def test_successful_create_activates_order():
    order = SimpleNamespace(status="provisioning")
    db = FakeDB(order)

    _synchronize_commercial_order_for_vps_job(
        db,
        vps=make_vps(),
        job=make_job("vps.create", "succeeded"),
    )

    assert order.status == "active"


def test_failed_create_marks_provisioning_failed():
    order = SimpleNamespace(status="provisioning")
    db = FakeDB(order)

    _synchronize_commercial_order_for_vps_job(
        db,
        vps=make_vps(),
        job=make_job("vps.create", "failed"),
    )

    assert order.status == "provisioning_failed"


def test_successful_delete_marks_order_deleted():
    order = SimpleNamespace(status="active")
    db = FakeDB(order)

    _synchronize_commercial_order_for_vps_job(
        db,
        vps=make_vps(),
        job=make_job("vps.delete", "succeeded"),
    )

    assert order.status == "deleted"


def test_failed_delete_marks_delete_failed():
    order = SimpleNamespace(status="active")
    db = FakeDB(order)

    _synchronize_commercial_order_for_vps_job(
        db,
        vps=make_vps(),
        job=make_job("vps.delete", "failed"),
    )

    assert order.status == "delete_failed"


def test_noncommercial_vps_is_noop():
    db = FakeDB(None)

    _synchronize_commercial_order_for_vps_job(
        db,
        vps=make_vps(),
        job=make_job("vps.create", "succeeded"),
    )


def test_unrelated_job_does_not_change_order():
    order = SimpleNamespace(status="active")
    db = FakeDB(order)

    _synchronize_commercial_order_for_vps_job(
        db,
        vps=make_vps(),
        job=make_job("vps.reboot", "succeeded"),
    )

    assert order.status == "active"
