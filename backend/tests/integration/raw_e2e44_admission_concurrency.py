"""RAW-E2E-44: real PostgreSQL admission locking checks.

Runs only against the isolated PostgreSQL instance.
Creates and drops its own temporary schema.
"""
import importlib
import pkgutil
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

import app.models
from app.models.base import Base
from app.models.node import Node
from app.models.compute import NodeCapacity, GamingSession, NodeJob
from app.models.user import User
from app.models.organization import Organization
from app.services.gaming_service import queue_gaming_action
from app.services.compute_service import ComputeError

for module in pkgutil.iter_modules(
    app.models.__path__, prefix="app.models."
):
    importlib.import_module(module.name)

SCHEMA = "raw_e2e44_admission_concurrency"
DATA_DIR = (
    "/home/khanadmin/raw-e2e39-recovery/"
    "postgres-concurrency"
)

url = URL.create(
    "postgresql+psycopg2",
    username="khanadmin",
    host="127.0.0.1",
    port=55439,
    database="raw_e2e39_concurrency",
)

admin = create_engine(url, future=True)
engine = create_engine(
    url,
    execution_options={
        "schema_translate_map": {None: SCHEMA}
    },
    future=True,
    pool_size=5,
    max_overflow=2,
)


def verify(conn):
    identity = tuple(conn.execute(text("""
        SELECT current_database(),
               inet_server_port(),
               current_setting('data_directory')
    """)).one())
    assert identity == (
        "raw_e2e39_concurrency",
        55439,
        DATA_DIR,
    ), identity


def fixture():
    suffix = uuid4().hex[:12]
    with Session(engine, autoflush=False) as db:
        user = User(
            email=f"admission-{suffix}@example.invalid",
            username=f"admission-{suffix}",
            full_name="Admission Test",
            password_hash="test-only",
            is_active=True,
        )
        db.add(user)
        db.flush()

        org = Organization(
            name=f"Admission {suffix}",
            slug=f"admission-{suffix}",
            created_by_user_id=user.id,
            is_active=True,
        )
        db.add(org)
        db.flush()

        node = Node(
            name=f"admission-host-{suffix}",
            machine_id=f"admission-host-{suffix}",
            hostname=f"admission-host-{suffix}",
            secret_hash="test-only",
            intended_purpose="gaming_host",
            lifecycle_state="approved",
            is_enabled=True,
            gaming_accepting_work=True,
            gaming_admission_auto_blocked=False,
        )
        db.add(node)
        db.flush()

        capacity = NodeCapacity(node_id=node.id)
        db.add(capacity)
        db.flush()

        gaming = GamingSession(
            organization_id=org.id,
            created_by_user_id=user.id,
            name=f"Admission Gaming {suffix}",
            node_id=node.id,
            status="stopped",
            desired_state="stopped",
        )
        db.add(gaming)
        db.commit()
        return node.id, gaming.id


def start_worker(gaming_id, barrier):
    with Session(engine, autoflush=False) as db:
        db.execute(text("SET LOCAL lock_timeout = '8s'"))
        session = db.get(GamingSession, gaming_id)
        barrier.wait(timeout=15)
        try:
            queue_gaming_action(
                db,
                session=session,
                action="start",
                commit=False,
            )
            db.commit()
            return "accepted"
        except ComputeError:
            db.rollback()
            return "rejected"


def test_duplicate_start():
    node_id, gaming_id = fixture()
    barrier = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(start_worker, gaming_id, barrier)
            for _ in range(2)
        ]
        results = [f.result(timeout=35) for f in futures]

    assert sorted(results) == ["accepted", "rejected"], results

    with Session(engine) as db:
        jobs = list(db.scalars(
            select(NodeJob).where(
                NodeJob.gaming_session_id == gaming_id,
                NodeJob.job_type.in_({
                    "gaming.session.start",
                    "gaming.vm.start",
                }),
            )
        ))
        assert len(jobs) == 1, len(jobs)

    print("DUPLICATE_START=PASS", flush=True)


def test_disabled_start():
    node_id, gaming_id = fixture()

    with Session(engine) as db:
        node = db.get(Node, node_id)
        node.gaming_accepting_work = False
        db.commit()

    with Session(engine, autoflush=False) as db:
        session = db.get(GamingSession, gaming_id)
        try:
            queue_gaming_action(
                db, session=session,
                action="start", commit=False,
            )
        except ComputeError:
            db.rollback()
        else:
            raise AssertionError("Disabled host accepted START")

    with Session(engine) as db:
        jobs = list(db.scalars(
            select(NodeJob).where(
                NodeJob.gaming_session_id == gaming_id
            )
        ))
        assert not jobs

    print("DISABLED_START=PASS", flush=True)



def test_admin_disable_race():
    from app.api.v1.nodes import set_gaming_availability
    from app.schemas.node import NodeGamingAvailabilityRequest

    node_id, gaming_id = fixture()
    barrier = threading.Barrier(2)

    def disable_worker():
        with Session(engine, autoflush=False) as db:
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            barrier.wait(timeout=15)
            set_gaming_availability(
                node_id=node_id,
                payload=NodeGamingAvailabilityRequest(
                    accepting_work=False,
                    reason="RAW-E2E-44 isolated race test",
                ),
                db=db,
            )
            return "disabled"

    with ThreadPoolExecutor(max_workers=2) as pool:
        start_future = pool.submit(
            start_worker, gaming_id, barrier
        )
        disable_future = pool.submit(disable_worker)
        start_result = start_future.result(timeout=35)
        disable_result = disable_future.result(timeout=35)

    assert disable_result == "disabled"

    with Session(engine) as db:
        node = db.get(Node, node_id)
        gaming = db.get(GamingSession, gaming_id)
        jobs = list(db.scalars(
            select(NodeJob).where(
                NodeJob.gaming_session_id == gaming_id,
                NodeJob.job_type.in_({
                    "gaming.session.start",
                    "gaming.vm.start",
                }),
            )
        ))

        assert node.gaming_accepting_work is False
        assert start_result in {"accepted", "rejected"}
        assert len(jobs) == (
            1 if start_result == "accepted" else 0
        )

        if start_result == "rejected":
            assert gaming.status == "stopped"
            assert gaming.desired_state == "stopped"

    # Once the administrative barrier has committed,
    # all subsequent START requests must be rejected.
    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        try:
            queue_gaming_action(
                db,
                session=gaming,
                action="start",
                commit=False,
            )
        except ComputeError:
            db.rollback()
        else:
            raise AssertionError(
                "START accepted after admission disabled"
            )

    print(
        f"ADMIN_DISABLE_RACE=PASS start={start_result}",
        flush=True,
    )



def test_start_drain_race():
    from app.services.gaming_service import request_gaming_node_drain

    node_id, gaming_id = fixture()
    barrier = threading.Barrier(2)

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        actor_id = gaming.created_by_user_id

    def drain_worker():
        with Session(engine, autoflush=False) as db:
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            node = db.get(Node, node_id)
            barrier.wait(timeout=15)

            result = request_gaming_node_drain(
                db,
                node=node,
                actor_user_id=actor_id,
                reason="RAW-E2E-44 isolated drain race",
                terminate_active_sessions=False,
            )
            return result.lifecycle_state

    with ThreadPoolExecutor(max_workers=2) as pool:
        start_future = pool.submit(
            start_worker, gaming_id, barrier
        )
        drain_future = pool.submit(drain_worker)

        start_result = start_future.result(timeout=35)
        drain_result = drain_future.result(timeout=35)

    assert drain_result == "draining"

    with Session(engine) as db:
        node = db.get(Node, node_id)
        gaming = db.get(GamingSession, gaming_id)
        jobs = list(db.scalars(
            select(NodeJob).where(
                NodeJob.gaming_session_id == gaming_id,
                NodeJob.job_type.in_({
                    "gaming.session.start",
                    "gaming.vm.start",
                }),
            )
        ))

        assert node.lifecycle_state == "draining"
        assert node.gaming_accepting_work is False
        assert start_result in {"accepted", "rejected"}
        assert len(jobs) == (
            1 if start_result == "accepted" else 0
        )

        if start_result == "rejected":
            assert gaming.status == "stopped"
            assert gaming.desired_state == "stopped"

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        try:
            queue_gaming_action(
                db,
                session=gaming,
                action="start",
                commit=False,
            )
        except ComputeError:
            db.rollback()
        else:
            raise AssertionError(
                "START accepted after drain committed"
            )

    print(
        f"START_DRAIN_RACE=PASS start={start_result}",
        flush=True,
    )



def test_capacity_lock_barrier():
    """Verify START waits for an administrator-held capacity lock."""
    import time

    node_id, gaming_id = fixture()
    locked = threading.Event()
    release = threading.Event()
    result = {}

    def administrator():
        with Session(engine, autoflush=False) as db:
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            capacity = db.scalar(
                select(NodeCapacity)
                .where(NodeCapacity.node_id == node_id)
                .with_for_update()
            )
            assert capacity is not None
            locked.set()
            assert release.wait(timeout=15)

            node = db.scalar(
                select(Node)
                .where(Node.id == node_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            node.gaming_accepting_work = False
            db.commit()

    def customer():
        assert locked.wait(timeout=15)
        with Session(engine, autoflush=False) as db:
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            gaming = db.get(GamingSession, gaming_id)
            try:
                queue_gaming_action(
                    db,
                    session=gaming,
                    action="start",
                    commit=False,
                )
                db.commit()
                result["start"] = "accepted"
            except ComputeError:
                db.rollback()
                result["start"] = "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        admin_future = pool.submit(administrator)
        assert locked.wait(timeout=15)
        start_future = pool.submit(customer)

        try:
            time.sleep(0.3)
            assert not start_future.done(), (
                "START completed before capacity lock release"
            )
        finally:
            release.set()

        admin_future.result(timeout=25)
        start_future.result(timeout=25)

    assert result.get("start") == "rejected", result

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        jobs = list(db.scalars(
            select(NodeJob).where(
                NodeJob.gaming_session_id == gaming_id
            )
        ))
        assert gaming.status == "stopped"
        assert gaming.desired_state == "stopped"
        assert not jobs

    print("CAPACITY_LOCK_BARRIER=PASS", flush=True)



def test_maintenance_reconciliation():
    from app.models.compute import GamingReservation
    from app.services.gaming_service import (
        reconcile_gaming_node_drain,
    )

    # Case 1: no ownership, maintenance allowed.
    node_id, gaming_id = fixture()

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        node.lifecycle_state = "draining"
        node.gaming_accepting_work = False
        db.commit()

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        assert reconcile_gaming_node_drain(
            db, node=node
        ) is True
        db.commit()

    with Session(engine) as db:
        node = db.get(Node, node_id)
        assert node.lifecycle_state == "maintenance"
        assert node.gaming_accepting_work is False

    print("MAINTENANCE_EMPTY=PASS", flush=True)

    # Case 2: active capacity ownership blocks maintenance.
    node_id, gaming_id = fixture()

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        node.lifecycle_state = "draining"
        node.gaming_accepting_work = False

        reservation = GamingReservation(
            gaming_session_id=gaming_id,
            node_id=node_id,
            gpu_uuid="test-gpu",
            cpu=2,
            memory_bytes=1024,
            storage_bytes=1024,
            status="reserved",
        )
        db.add(reservation)
        db.commit()

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        assert reconcile_gaming_node_drain(
            db, node=node
        ) is False
        db.commit()

    with Session(engine) as db:
        node = db.get(Node, node_id)
        assert node.lifecycle_state == "draining"

    print("MAINTENANCE_RESERVATION_BLOCK=PASS", flush=True)

    # Case 3: unfinished gaming work blocks maintenance.
    node_id, gaming_id = fixture()

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        node.lifecycle_state = "draining"
        node.gaming_accepting_work = False

        db.add(NodeJob(
            node_id=node_id,
            gaming_session_id=gaming_id,
            job_type="gaming.session.stop",
            status="pending",
            payload={},
        ))
        db.commit()

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        assert reconcile_gaming_node_drain(
            db, node=node
        ) is False
        db.commit()

    with Session(engine) as db:
        node = db.get(Node, node_id)
        assert node.lifecycle_state == "draining"

    print("MAINTENANCE_INFLIGHT_BLOCK=PASS", flush=True)



def test_rejected_start_financial_integrity():
    """Rejected START must leave finalized billing and ledger untouched."""
    from datetime import UTC, datetime

    from sqlalchemy import func
    from app.models.commercial import ProductCatalogItem, ProductSKU
    from app.models.finance import (
        CustomerWallet, UsageReservation,
        LedgerTransaction, LedgerEntry,
    )
    from app.services.billing_service import ledger_authoritative_topup
    from app.services.wallet_service import reserve_funds, wallet_balances
    from app.services.gaming_service import queue_gaming_action

    node_id, gaming_id = fixture()
    suffix = uuid4().hex[:12]

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)

        product = ProductCatalogItem(
            code=f"financial-{suffix}",
            workload_type="gaming",
            name="Financial Integrity Test",
            currency="USD",
            is_active=True,
            is_sellable=True,
        )
        db.add(product)
        db.flush()

        sku = ProductSKU(
            product_id=product.id,
            code=f"financial-sku-{suffix}",
            name="Financial Test SKU",
            billing_mode="metered",
            is_active=True,
            is_sellable=True,
        )
        db.add(sku)
        db.flush()

        wallet, _, _ = ledger_authoritative_topup(
            db,
            organization_id=gaming.organization_id,
            user_id=gaming.created_by_user_id,
            currency="USD",
            amount_minor=10000,
            provider="raw_e2e44_test",
            provider_reference=f"financial:{suffix}:deposit",
        )

        reservation = reserve_funds(
            db,
            wallet=wallet,
            amount_minor=2000,
            idempotency_key=f"financial:{suffix}:reserve",
            reference_type="gaming_session",
            reference_id=str(gaming_id),
        )

        gaming.product_sku_id = sku.id
        gaming.usage_reservation_id = reservation.id
        gaming.billing_currency = "USD"
        gaming.per_minute_price_minor = 100
        gaming.billing_finalized_at = datetime.now(UTC)
        gaming.billing_stop_reason = "customer_stop"
        gaming.status = "stopped"
        gaming.desired_state = "stopped"

        node = db.get(Node, node_id)
        node.gaming_accepting_work = False

        db.commit()

    def snapshot():
        with Session(engine, autoflush=False) as db:
            gaming = db.get(GamingSession, gaming_id)
            wallet = db.scalar(
                select(CustomerWallet).where(
                    CustomerWallet.organization_id ==
                    gaming.organization_id,
                    CustomerWallet.currency == "USD",
                )
            )
            assert wallet is not None

            balances = wallet_balances(db, wallet)

            def count(model):
                return db.scalar(
                    select(func.count()).select_from(model)
                )

            return {
                "balances": balances,
                "transactions": count(LedgerTransaction),
                "entries": count(LedgerEntry),
                "reservations": count(UsageReservation),
                "reservation_id": gaming.usage_reservation_id,
                "finalized_at": gaming.billing_finalized_at,
                "stop_reason": gaming.billing_stop_reason,
                "status": gaming.status,
                "desired_state": gaming.desired_state,
                "jobs": count(NodeJob),
            }

    before = snapshot()

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        try:
            queue_gaming_action(
                db,
                session=gaming,
                action="start",
                commit=False,
            )
        except ComputeError:
            db.rollback()
        else:
            db.rollback()
            raise AssertionError(
                "Disabled gaming host unexpectedly accepted START"
            )

    after = snapshot()

    assert after == before, {
        "before": before,
        "after": after,
    }

    print("REJECTED_START_WALLET_UNCHANGED=PASS", flush=True)
    print("REJECTED_START_LEDGER_UNCHANGED=PASS", flush=True)
    print("REJECTED_START_BILLING_FINALIZED=PASS", flush=True)
    print("REJECTED_START_NO_JOB=PASS", flush=True)



def test_maintenance_capacity_lock_barrier():
    import time
    from app.services.gaming_service import (
        reconcile_gaming_node_drain,
    )

    node_id, gaming_id = fixture()

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        node.lifecycle_state = "draining"
        node.gaming_accepting_work = False
        db.commit()

    locked = threading.Event()
    release = threading.Event()
    result = {}

    def administrator():
        with Session(engine, autoflush=False) as db:
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            capacity = db.scalar(
                select(NodeCapacity)
                .where(NodeCapacity.node_id == node_id)
                .with_for_update()
            )
            assert capacity is not None
            locked.set()
            assert release.wait(timeout=15)
            db.commit()

    def reconciler():
        assert locked.wait(timeout=15)
        with Session(engine, autoflush=False) as db:
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            node = db.get(Node, node_id)
            result["changed"] = reconcile_gaming_node_drain(
                db, node=node
            )
            db.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        admin_future = pool.submit(administrator)
        assert locked.wait(timeout=15)
        reconcile_future = pool.submit(reconciler)

        try:
            time.sleep(0.3)
            assert not reconcile_future.done(), (
                "Maintenance bypassed capacity lock"
            )
        finally:
            release.set()

        admin_future.result(timeout=25)
        reconcile_future.result(timeout=25)

    assert result.get("changed") is True, result

    with Session(engine) as db:
        node = db.get(Node, node_id)
        assert node.lifecycle_state == "maintenance"

    print("MAINTENANCE_CAPACITY_LOCK_BARRIER=PASS", flush=True)



def test_concurrent_financial_restart():
    """Two simultaneous restarts must create one financial generation."""
    from datetime import UTC, datetime

    from sqlalchemy import func
    from app.models.commercial import ProductCatalogItem, ProductSKU
    from app.models.finance import (
        CustomerWallet, UsageReservation,
        LedgerTransaction, LedgerEntry,
    )
    from app.services.billing_service import ledger_authoritative_topup
    from app.services.wallet_service import reserve_funds, wallet_balances
    from app.services.billing_policy import METERED_MINIMUM_START_MINUTES

    node_id, gaming_id = fixture()
    suffix = uuid4().hex[:12]

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)

        product = ProductCatalogItem(
            code=f"restart-{suffix}",
            workload_type="gaming",
            name="Restart Financial Test",
            currency="USD",
            is_active=True,
            is_sellable=True,
        )
        db.add(product)
        db.flush()

        sku = ProductSKU(
            product_id=product.id,
            code=f"restart-sku-{suffix}",
            name="Restart Test SKU",
            billing_mode="metered",
            is_active=True,
            is_sellable=True,
        )
        db.add(sku)
        db.flush()

        wallet, _, _ = ledger_authoritative_topup(
            db,
            organization_id=gaming.organization_id,
            user_id=gaming.created_by_user_id,
            currency="USD",
            amount_minor=10000,
            provider="raw_e2e45_test",
            provider_reference=f"restart:{suffix}:deposit",
        )

        previous = reserve_funds(
            db,
            wallet=wallet,
            amount_minor=2000,
            idempotency_key=f"restart:{suffix}:previous",
            reference_type="gaming_session",
            reference_id=str(gaming_id),
        )

        from app.services.wallet_service import release_reservation

        release_reservation(
            db,
            reservation=previous,
            amount_minor=2000,
            idempotency_key=f"restart:{suffix}:previous:release",
        )

        assert previous.reserved_minor == (
            previous.consumed_minor + previous.released_minor
        )
        assert previous.status == "closed"

        gaming.product_sku_id = sku.id
        gaming.usage_reservation_id = previous.id
        gaming.billing_currency = "USD"
        gaming.per_minute_price_minor = 100
        gaming.billing_finalized_at = datetime.now(UTC)
        gaming.billing_stop_reason = "customer_stop"
        gaming.status = "stopped"
        gaming.desired_state = "stopped"
        db.commit()
        previous_id = previous.id

    def snapshot():
        with Session(engine, autoflush=False) as db:
            gaming = db.get(GamingSession, gaming_id)
            wallet = db.scalar(
                select(CustomerWallet).where(
                    CustomerWallet.organization_id == gaming.organization_id,
                    CustomerWallet.currency == "USD",
                )
            )
            assert wallet is not None
            def count(model):
                return db.scalar(
                    select(func.count()).select_from(model)
                )
            return {
                "balances": wallet_balances(db, wallet),
                "transactions": count(LedgerTransaction),
                "entries": count(LedgerEntry),
                "reservations": count(UsageReservation),
                "jobs": count(NodeJob),
            }

    before = snapshot()
    barrier = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(start_worker, gaming_id, barrier)
            for _ in range(2)
        ]
        results = [f.result(timeout=40) for f in futures]

    assert results.count("accepted") == 1, results
    assert results.count("rejected") == 1, results

    after = snapshot()
    expected_amount = 100 * int(METERED_MINIMUM_START_MINUTES)

    assert after["reservations"] == before["reservations"] + 1
    assert after["transactions"] == before["transactions"] + 1
    assert after["entries"] == before["entries"] + 2
    assert after["jobs"] == before["jobs"] + 1

    assert (
        after["balances"]["available_minor"]
        == before["balances"]["available_minor"] - expected_amount
    )
    assert (
        after["balances"]["reserved_minor"]
        == before["balances"]["reserved_minor"] + expected_amount
    )

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.status == "starting"
        assert gaming.desired_state == "running"
        assert gaming.billing_finalized_at is None
        assert gaming.usage_reservation_id != previous_id

        new_reservation = db.get(
            UsageReservation, gaming.usage_reservation_id
        )
        assert new_reservation is not None
        assert new_reservation.reserved_minor == expected_amount
        assert new_reservation.reference_type == "gaming_session_restart"

        jobs = list(
            db.scalars(
                select(NodeJob).where(
                    NodeJob.gaming_session_id == gaming_id,
                    NodeJob.job_type.in_({
                        "gaming.session.start",
                        "gaming.vm.start",
                    }),
                )
            )
        )
        assert len(jobs) == 1
        assert (
            jobs[0].payload["billing_generation"]
            == str(new_reservation.id)
        )

    print("CONCURRENT_FINANCIAL_START_SINGLE_ACCEPT=PASS", flush=True)
    print("RESTART_SINGLE_RESERVATION=PASS", flush=True)
    print("RESTART_SINGLE_LEDGER_TRANSACTION=PASS", flush=True)
    print("RESTART_WALLET_BALANCE_EXACT=PASS", flush=True)
    print("RESTART_JOB_BILLING_GENERATION=PASS", flush=True)

    from app.services.compute_service import finish_job

    start_id = jobs[0].id
    reservation_id = new_reservation.id

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=start_id,
            status="succeeded", result={}, error_message="",
        )

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.status == "running"
        assert gaming.started_at is not None
        assert gaming.usage_reservation_id == reservation_id
        started_at = gaming.started_at

    with Session(engine) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=start_id,
            status="succeeded", result={}, error_message="",
        )

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.started_at == started_at

    print("FUNDED_START_CALLBACK_IDEMPOTENT=PASS", flush=True)

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        queue_gaming_action(
            db, session=gaming, action="stop",
            stop_reason="customer_stop", commit=False,
        )
        db.commit()

        stop = db.scalar(select(NodeJob).where(
            NodeJob.gaming_session_id == gaming_id,
            NodeJob.job_type == "gaming.session.stop",
        ))
        assert stop is not None
        assert stop.payload["billing_generation"] == str(reservation_id)
        stop_id = stop.id

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=stop_id,
            status="succeeded", result={}, error_message="",
        )

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        reservation = db.get(UsageReservation, reservation_id)
        previous = db.get(UsageReservation, previous_id)

        assert gaming.status == "stopped"
        assert gaming.billing_finalized_at is not None
        assert reservation.status == "closed"
        assert reservation.reserved_minor == (
            reservation.consumed_minor + reservation.released_minor
        )
        assert previous.status == "closed"
        assert previous.released_minor == 2000

        settled = snapshot()
        finalized_at = gaming.billing_finalized_at
        released_minor = reservation.released_minor
        consumed_minor = reservation.consumed_minor

        assert (
            settled["balances"]["available_minor"]
            == before["balances"]["available_minor"] - consumed_minor
        )
        assert (
            settled["balances"]["reserved_minor"]
            == before["balances"]["reserved_minor"]
        )

    print("FUNDED_STOP_RESERVATION_CLOSED=PASS", flush=True)
    print("FUNDED_STOP_WALLET_EXACT=PASS", flush=True)

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=stop_id,
            status="succeeded", result={}, error_message="",
        )

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        reservation = db.get(UsageReservation, reservation_id)

        assert gaming.billing_finalized_at == finalized_at
        assert reservation.released_minor == released_minor
        assert reservation.consumed_minor == consumed_minor

        repeated = snapshot()
        assert repeated == settled

    print("FUNDED_DUPLICATE_STOP_NO_DOUBLE_SETTLEMENT=PASS", flush=True)



def test_financial_callback_lifecycle():
    """Verify restart callback idempotency and settlement."""
    from sqlalchemy import func
    from app.models.finance import (
        UsageReservation, LedgerTransaction, LedgerEntry,
    )
    from app.services.compute_service import finish_job

    node_id, gaming_id = fixture()

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        queue_gaming_action(
            db, session=gaming, action="start", commit=False,
        )
        db.commit()

        start = db.scalar(select(NodeJob).where(
            NodeJob.gaming_session_id == gaming_id,
            NodeJob.job_type == "gaming.session.start",
        ))
        assert start is not None
        start_id = start.id

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=start_id,
            status="succeeded",
            result={"deployment_stage": "stream_ready"},
            error_message="",
        )

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.status == "running"
        assert gaming.started_at is not None
        assert gaming.last_metered_at is None
        started_at = gaming.started_at

    print("START_CALLBACK_RUNNING=PASS", flush=True)

    with Session(engine) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=start_id,
            status="succeeded",
            result={},
            error_message="",
        )

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.started_at == started_at

    print("DUPLICATE_START_CALLBACK_IDEMPOTENT=PASS", flush=True)

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        queue_gaming_action(
            db, session=gaming, action="stop",
            commit=False, stop_reason="customer_stop",
        )
        db.commit()

        stop = db.scalar(select(NodeJob).where(
            NodeJob.gaming_session_id == gaming_id,
            NodeJob.job_type == "gaming.session.stop",
        ))
        assert stop is not None
        stop_id = stop.id

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=stop_id,
            status="succeeded", result={}, error_message="",
        )

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.status == "stopped"
        assert gaming.billing_finalized_at is not None
        finalized_at = gaming.billing_finalized_at

        transaction_count = db.scalar(
            select(func.count()).select_from(LedgerTransaction)
        )

    print("STOP_CALLBACK_FINALIZED=PASS", flush=True)

    with Session(engine) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=stop_id,
            status="succeeded", result={}, error_message="",
        )

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.billing_finalized_at == finalized_at
        assert db.scalar(
            select(func.count()).select_from(LedgerTransaction)
        ) == transaction_count

    print("DUPLICATE_STOP_SETTLEMENT_PREVENTED=PASS", flush=True)



def test_failed_start_retains_ownership():
    """A failed START cannot prove runtime/GPU ownership is gone."""
    from app.services.compute_service import finish_job

    node_id, gaming_id = fixture()

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        queue_gaming_action(
            db, session=gaming, action="start", commit=False,
        )
        db.commit()

        job = db.scalar(select(NodeJob).where(
            NodeJob.gaming_session_id == gaming_id,
            NodeJob.job_type == "gaming.session.start",
        ))
        assert job is not None
        job_id = job.id

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=job_id,
            status="failed", result={},
            error_message="isolated simulated start failure",
        )

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.status == "error"
        assert gaming.desired_state == "running"
        assert gaming.billing_finalized_at is None
        assert gaming.failure_category == "node_job_failed"

    print("FAILED_START_RETAINS_SESSION_OWNERSHIP=PASS", flush=True)


def test_stale_start_generation_ignored():
    """An outdated generation must not transition the session."""
    from app.services.compute_service import finish_job
    from uuid import uuid4

    node_id, gaming_id = fixture()

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        queue_gaming_action(
            db, session=gaming, action="start", commit=False,
        )
        db.commit()

        job = db.scalar(select(NodeJob).where(
            NodeJob.gaming_session_id == gaming_id,
            NodeJob.job_type == "gaming.session.start",
        ))
        assert job is not None
        job_id = job.id

        payload = dict(job.payload or {})
        payload["billing_generation"] = str(uuid4())
        job.payload = payload
        db.commit()

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=job_id,
            status="succeeded", result={},
            error_message="",
        )

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        job = db.get(NodeJob, job_id)
        assert job.status == "succeeded"
        assert gaming.status == "starting"
        assert gaming.desired_state == "running"
        assert gaming.started_at is None

    print("STALE_START_GENERATION_IGNORED=PASS", flush=True)



def test_funded_failed_start_retains_ownership():
    """Failed funded START retains wallet hold and existing GPU ownership."""
    from datetime import UTC, datetime
    from sqlalchemy import func
    from app.models.compute import GamingReservation
    from app.models.commercial import ProductCatalogItem, ProductSKU
    from app.models.finance import (
        CustomerWallet, UsageReservation, LedgerTransaction, LedgerEntry,
    )
    from app.services.billing_service import ledger_authoritative_topup
    from app.services.wallet_service import wallet_balances
    from app.services.compute_service import finish_job
    from app.services.billing_policy import METERED_MINIMUM_START_MINUTES

    node_id, gaming_id = fixture()
    suffix = uuid4().hex[:12]

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        capacity = db.scalar(select(NodeCapacity).where(
            NodeCapacity.node_id == node_id
        ))

        product = ProductCatalogItem(
            code=f"failed-start-{suffix}",
            workload_type="gaming",
            name="Failed START Test",
            currency="USD",
            is_active=True,
            is_sellable=True,
        )
        db.add(product)
        db.flush()

        sku = ProductSKU(
            product_id=product.id,
            code=f"failed-start-sku-{suffix}",
            name="Failed START SKU",
            billing_mode="metered",
            is_active=True,
            is_sellable=True,
        )
        db.add(sku)
        db.flush()

        ledger_authoritative_topup(
            db,
            organization_id=gaming.organization_id,
            user_id=gaming.created_by_user_id,
            currency="USD",
            amount_minor=10000,
            provider="raw_e2e45_test",
            provider_reference=f"failed-start:{suffix}:deposit",
        )

        gaming.product_sku_id = sku.id
        gaming.billing_currency = "USD"
        gaming.per_minute_price_minor = 100

        # Model a completed previous billing generation.
        # START must open a new funded reservation.
        gaming.billing_finalized_at = datetime.now(UTC)
        gaming.billing_stop_reason = "customer_stop"
        gaming.status = "stopped"
        gaming.desired_state = "stopped"

        # Existing session ownership, not a new allocation by START.
        gpu = GamingReservation(
            gaming_session_id=gaming_id,
            node_id=node_id,
            gpu_uuid=f"isolated-gpu-{suffix}",
            cpu=2,
            memory_bytes=4 * 1024**3,
            storage_bytes=20 * 1024**3,
            status="active",
        )
        db.add(gpu)
        capacity.cpu_allocated = 2
        capacity.memory_allocated_bytes = 4 * 1024**3
        capacity.storage_allocated_bytes = 20 * 1024**3
        db.commit()
        gpu_id = gpu.id

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        queue_gaming_action(
            db, session=gaming, action="start", commit=False,
        )
        db.commit()

        job = db.scalar(select(NodeJob).where(
            NodeJob.gaming_session_id == gaming_id,
            NodeJob.job_type == "gaming.session.start",
        ))
        assert job is not None
        job_id = job.id

        gaming = db.get(GamingSession, gaming_id)
        reservation_id = gaming.usage_reservation_id
        assert reservation_id is not None
        assert job.payload["billing_generation"] == str(reservation_id)

    def snapshot():
        with Session(engine, autoflush=False) as db:
            gaming = db.get(GamingSession, gaming_id)
            reservation = db.get(UsageReservation, reservation_id)
            gpu = db.get(GamingReservation, gpu_id)
            capacity = db.scalar(select(NodeCapacity).where(
                NodeCapacity.node_id == node_id
            ))
            wallet = db.get(CustomerWallet, reservation.wallet_id)

            def count(model):
                return db.scalar(
                    select(func.count()).select_from(model)
                )

            return {
                "wallet": wallet_balances(db, wallet),
                "ledger_transactions": count(LedgerTransaction),
                "ledger_entries": count(LedgerEntry),
                "usage_reservations": count(UsageReservation),
                "reserved_minor": reservation.reserved_minor,
                "consumed_minor": reservation.consumed_minor,
                "released_minor": reservation.released_minor,
                "reservation_status": reservation.status,
                "gpu_status": gpu.status,
                "gpu_released_at": gpu.released_at,
                "cpu_allocated": capacity.cpu_allocated,
                "memory_allocated": capacity.memory_allocated_bytes,
                "storage_allocated": capacity.storage_allocated_bytes,
                "billing_finalized_at": gaming.billing_finalized_at,
            }

    before = snapshot()
    expected_hold = 100 * int(METERED_MINIMUM_START_MINUTES)

    assert before["reserved_minor"] == expected_hold
    assert before["consumed_minor"] == 0
    assert before["released_minor"] == 0
    assert before["reservation_status"] == "reserved"
    assert before["gpu_status"] == "active"
    assert before["gpu_released_at"] is None
    assert before["cpu_allocated"] == 2
    assert before["memory_allocated"] == 4 * 1024**3
    assert before["storage_allocated"] == 20 * 1024**3
    assert before["wallet"]["reserved_minor"] == expected_hold

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db, node=node, job_id=job_id,
            status="failed", result={},
            error_message="isolated funded START failure",
        )

    after = snapshot()
    assert after == before, (before, after)

    with Session(engine) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.status == "error"
        assert gaming.desired_state == "running"
        assert gaming.failure_category == "node_job_failed"

    print("FUNDED_FAILED_START_WALLET_RETAINED=PASS", flush=True)
    print("FUNDED_FAILED_START_LEDGER_UNCHANGED=PASS", flush=True)
    print("FUNDED_FAILED_START_RESERVATION_RETAINED=PASS", flush=True)
    print("FUNDED_FAILED_START_GPU_RETAINED=PASS", flush=True)
    print("FUNDED_FAILED_START_CAPACITY_RETAINED=PASS", flush=True)

def main():
    with admin.begin() as conn:
        verify(conn)
        exists = conn.execute(text("""
            SELECT 1 FROM information_schema.schemata
            WHERE schema_name = :schema
        """), {"schema": SCHEMA}).scalar()
        assert not exists, "Temporary schema already exists"
        conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))

    try:
        Base.metadata.create_all(engine)
        print("ISOLATED_SCHEMA=PASS", flush=True)
        test_duplicate_start()
        test_disabled_start()
        test_admin_disable_race()
        test_start_drain_race()
        test_capacity_lock_barrier()
        test_maintenance_reconciliation()
        test_maintenance_capacity_lock_barrier()
        test_rejected_start_financial_integrity()
        test_concurrent_financial_restart()
        test_financial_callback_lifecycle()
        test_failed_start_retains_ownership()
        test_stale_start_generation_ignored()
        test_funded_failed_start_retains_ownership()
        print("RAW_E2E44_INITIAL_CONCURRENCY=PASS", flush=True)
    finally:
        with admin.begin() as conn:
            verify(conn)
            conn.execute(text(
                f'DROP SCHEMA "{SCHEMA}" CASCADE'
            ))
        print("TEMPORARY_SCHEMA_CLEANED=PASS", flush=True)


if __name__ == "__main__":
    main()
