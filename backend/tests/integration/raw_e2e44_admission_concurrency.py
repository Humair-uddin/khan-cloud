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
