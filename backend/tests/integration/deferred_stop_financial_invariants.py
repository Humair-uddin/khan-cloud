import importlib
import pkgutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

import app.models
from app.models.base import Base
from app.models.user import User
from app.models.organization import Organization
from app.models.node import Node
from app.models.compute import GamingSession
from app.models.commercial import ProductCatalogItem, ProductSKU
from app.models.finance import LedgerTransaction, LedgerEntry
from app.services.billing_service import ledger_authoritative_topup
from app.services.wallet_service import reserve_funds
from app.services.gaming_billing_service import meter_gaming_session

for module in pkgutil.iter_modules(
    app.models.__path__, prefix="app.models."
):
    importlib.import_module(module.name)

SCHEMA = "raw_e2e39_permanent_financial"

url = URL.create(
    "postgresql+psycopg2",
    username="khanadmin",
    host="127.0.0.1",
    port=55439,
    database="raw_e2e39_concurrency",
)

admin_engine = create_engine(url, future=True)

def verify(conn):
    identity = tuple(conn.execute(text("""
        SELECT current_database(),
               inet_server_port(),
               current_setting('data_directory')
    """)).one())

    assert identity == (
        "raw_e2e39_concurrency",
        55439,
        "/home/khanadmin/raw-e2e39-recovery/postgres-concurrency",
    ), identity

with admin_engine.begin() as conn:
    verify(conn)
    exists = conn.execute(text("""
        SELECT 1 FROM information_schema.schemata
        WHERE schema_name = :schema
    """), {"schema": SCHEMA}).scalar()

    assert not exists, "Test schema already exists"
    conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))

print("DATABASE_IDENTITY=PASS", flush=True)

engine = create_engine(
    url,
    execution_options={"schema_translate_map": {None: SCHEMA}},
    future=True,
    pool_size=5,
    max_overflow=2,
)

try:
    Base.metadata.create_all(engine)
    print("TEMPORARY_SCHEMA=CREATED", flush=True)

    suffix = uuid4().hex[:12]
    start = datetime.now(UTC) - timedelta(minutes=3)
    now = start + timedelta(minutes=3)

    with Session(engine, autoflush=False) as db:
        user = User(
            email=f"concurrent-{suffix}@example.invalid",
            username=f"concurrent-{suffix}",
            full_name="Concurrent Billing Test",
            password_hash="test-only",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()

        org = Organization(
            name=f"Concurrent E2E39 {suffix}",
            slug=f"concurrent-e2e39-{suffix}",
            created_by_user_id=user.id,
            is_active=True,
        )
        db.add(org)
        db.flush()

        host = Node(
            name=f"host-{suffix}",
            machine_id=f"host-{suffix}",
            secret_hash="test-only",
            hostname=f"host-{suffix}",
            last_seen_at=datetime.now(UTC),
        )
        db.add(host)
        db.flush()

        product = ProductCatalogItem(
            code=f"product-{suffix}",
            workload_type="gaming",
            name="Concurrent Gaming Product",
            currency="USD",
            is_active=True,
            is_sellable=True,
        )
        db.add(product)
        db.flush()

        sku = ProductSKU(
            product_id=product.id,
            code=f"sku-{suffix}",
            name="Concurrent Gaming SKU",
            billing_mode="metered",
            is_active=True,
            is_sellable=True,
        )
        db.add(sku)
        db.flush()

        wallet, _, _ = ledger_authoritative_topup(
            db,
            organization_id=org.id,
            user_id=user.id,
            currency="USD",
            amount_minor=10000,
            provider="raw_e2e39_test",
            provider_reference=f"concurrent:{suffix}:deposit",
        )

        reservation = reserve_funds(
            db,
            wallet=wallet,
            amount_minor=5000,
            idempotency_key=f"concurrent:{suffix}:reserve",
            reference_type="gaming_session",
            reference_id=f"concurrent:{suffix}",
        )

        gaming = GamingSession(
            organization_id=org.id,
            created_by_user_id=user.id,
            name=f"Concurrent Gaming {suffix}",
            node_id=host.id,
            product_sku_id=sku.id,
            status="running",
            started_at=start,
            last_metered_at=start,
            usage_reservation_id=reservation.id,
            billing_currency="USD",
            per_minute_price_minor=100,
            host_payout_per_minute_minor=0,
        )
        db.add(gaming)
        db.commit()

        gaming_id = gaming.id
        reservation_id = reservation.id

    print("COMMITTED_FIXTURE=PASS", flush=True)


    from app.models.compute import NodeJob
    from app.models.finance import UsageReservation
    from app.services.gaming_billing_service import finalize_gaming_billing
    from app.services.gaming_service import queue_gaming_action
    from app.services.compute_service import ComputeError

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        finalize_gaming_billing(
            db,
            session=gaming,
            reason="customer_stop",
        )
        gaming.status = "stopped"
        gaming.desired_state = "stopped"
        db.commit()

    print("STOPPED_FIXTURE=PASS", flush=True)

    barrier = threading.Barrier(2)

    def start_worker(number):
        with Session(engine, autoflush=False) as db:
            db.execute(text("SET LOCAL lock_timeout = '8s'"))
            gaming = db.get(GamingSession, gaming_id)
            assert gaming is not None

            barrier.wait(timeout=15)

            try:
                queue_gaming_action(
                    db,
                    session=gaming,
                    action="start",
                    commit=False,
                )
                db.commit()
                return number, "accepted"
            except ComputeError as exc:
                db.rollback()
                return number, "rejected", str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(start_worker, number)
            for number in (1, 2)
        ]
        results = [f.result(timeout=40) for f in futures]

    print(f"START_RESULTS={results}", flush=True)

    accepted = [r for r in results if r[1] == "accepted"]
    rejected = [r for r in results if r[1] == "rejected"]

    assert len(accepted) == 1, results
    assert len(rejected) == 1, results

    print("EXACTLY_ONE_START_ACCEPTED=PASS", flush=True)

    with Session(engine, autoflush=False) as db:
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

        assert len(jobs) == 1, len(jobs)
        assert jobs[0].status in {"pending", "running"}
        assert gaming.status == "starting"
        assert gaming.desired_state == "running"

        new_generation = gaming.usage_reservation_id
        assert new_generation is not None
        assert new_generation != reservation_id

        new_reservation = db.get(
            UsageReservation,
            new_generation,
        )
        assert new_reservation is not None

        assert (
            jobs[0].payload.get("billing_generation")
            == str(new_generation)
        )

    print("SINGLE_PENDING_START_JOB=PASS", flush=True)
    print("NEW_BILLING_GENERATION=PASS", flush=True)
    print("CONCURRENT_START_ADMISSION=PASS", flush=True)

    print("===== STOP WHILE START IS PENDING =====", flush=True)

    with Session(engine, autoflush=False) as db:
        db.execute(text("SET LOCAL lock_timeout = '8s'"))
        gaming = db.get(GamingSession, gaming_id)

        assert gaming.status == "starting"
        assert gaming.desired_state == "running"

        try:
            queue_gaming_action(
                db,
                session=gaming,
                action="stop",
                commit=False,
                stop_reason="customer_stop",
            )
        except ComputeError as exc:
            print(f"STOP_RESULT=REJECTED: {exc}", flush=True)
            db.rollback()
        else:
            print("STOP_RESULT=ACCEPTED", flush=True)
            db.commit()

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        jobs = list(db.scalars(
            select(NodeJob).where(
                NodeJob.gaming_session_id == gaming_id
            )
        ))

        print(f"FINAL_DESIRED_STATE={gaming.desired_state}", flush=True)
        print(f"FINAL_SESSION_STATUS={gaming.status}", flush=True)
        print(
            "JOB_TYPES="
            + repr([(j.job_type, j.status) for j in jobs]),
            flush=True,
        )

        assert len(jobs) >= 1

    print("STOP_ADMISSION_BEHAVIOR_CAPTURED=PASS", flush=True)

    print("===== DEFERRED START CALLBACK =====", flush=True)

    from app.services.compute_service import finish_job

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        host = db.get(Node, gaming.node_id)
        host_id = host.id
        starts = list(db.scalars(
            select(NodeJob).where(
                NodeJob.gaming_session_id == gaming_id,
                NodeJob.job_type.in_({
                    "gaming.session.start", "gaming.vm.start"
                }),
            )
        ))
        assert len(starts) == 1
        start_job_id = starts[0].id
        generation = gaming.usage_reservation_id
        before_started = gaming.started_at
        before_metered = gaming.last_metered_at
        print(f"BEFORE_STARTED_AT={before_started}", flush=True)
        print(f"BEFORE_LAST_METERED_AT={before_metered}", flush=True)
        assert generation is not None
        assert gaming.desired_state == "stopped"

        finish_job(
            db,
            node=host,
            job_id=start_job_id,
            status="succeeded",
            result={"deployment_stage": "stream_ready"},
            error_message="",
        )

    print("START_CALLBACK=COMPLETED", flush=True)

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        jobs = list(db.scalars(
            select(NodeJob).where(
                NodeJob.gaming_session_id == gaming_id
            )
        ))
        starts = [
            j for j in jobs
            if j.job_type in {
                "gaming.session.start", "gaming.vm.start"
            }
        ]
        stops = [
            j for j in jobs
            if j.job_type in {
                "gaming.session.stop", "gaming.vm.stop"
            }
        ]

        assert len(starts) == 1
        assert starts[0].status == "succeeded"
        assert len(stops) == 1, [
            (j.job_type, j.status) for j in jobs
        ]
        assert stops[0].status == "pending"
        assert gaming.desired_state == "stopped"
        assert gaming.status == "stopping"
        assert stops[0].payload.get(
            "billing_generation"
        ) == str(generation)
        assert gaming.usage_reservation_id == generation

        stop_job_id = stops[0].id
        print("AUTOMATIC_STOP_DISPATCH=PASS", flush=True)
        print("STOP_GENERATION=PASS", flush=True)
        print(f"AFTER_STARTED_AT={gaming.started_at}", flush=True)
        print(f"AFTER_LAST_METERED_AT={gaming.last_metered_at}", flush=True)

    with Session(engine, autoflush=False) as db:
        host = db.get(Node, host_id)
        finish_job(
            db,
            node=host,
            job_id=start_job_id,
            status="succeeded",
            result={"deployment_stage": "stream_ready"},
            error_message="",
        )

    with Session(engine, autoflush=False) as db:
        jobs = list(db.scalars(
            select(NodeJob).where(
                NodeJob.gaming_session_id == gaming_id,
                NodeJob.job_type.in_({
                    "gaming.session.stop", "gaming.vm.stop"
                }),
            )
        ))
        assert len(jobs) == 1
        print("DUPLICATE_START_CALLBACK=PASS", flush=True)


    print("===== FINANCIAL INTERVAL SETUP =====", flush=True)

    from sqlalchemy import update

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.last_metered_at is not None
        assert gaming.started_at is not None

        billing_start = datetime.now(UTC) - timedelta(minutes=3)
        gaming.started_at = billing_start
        gaming.last_metered_at = billing_start

        host = db.get(Node, gaming.node_id)
        host.last_seen_at = datetime.now(UTC)

        reservation = db.get(
            UsageReservation, gaming.usage_reservation_id
        )
        print(
            f"RESERVATION_BEFORE={reservation.status}",
            flush=True,
        )
        print(
            f"BILLING_START={billing_start}",
            flush=True,
        )
        db.commit()

    print("BILLING_INTERVAL_PREPARED=PASS", flush=True)

    print("===== STOP COMPLETION =====", flush=True)

    with Session(engine, autoflush=False) as db:
        host = db.get(Node, host_id)
        finish_job(
            db,
            node=host,
            job_id=stop_job_id,
            status="succeeded",
            result={},
            error_message="",
        )

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        reservation = db.get(
            UsageReservation, generation
        )
        assert gaming.status == "stopped"
        assert gaming.desired_state == "stopped"
        assert gaming.usage_reservation_id == generation
        assert reservation is not None
        assert gaming.billing_finalized_at is not None
        assert gaming.billing_stop_reason == "customer_stop"
        print(f"BILLING_FINALIZED_AT={gaming.billing_finalized_at}", flush=True)
        print(f"BILLING_STOP_REASON={gaming.billing_stop_reason}", flush=True)
        print(f"RESERVATION_STATUS={reservation.status}", flush=True)
        print(f"FINAL_STARTED_AT={gaming.started_at}", flush=True)
        print(f"FINAL_LAST_METERED_AT={gaming.last_metered_at}", flush=True)

        print("===== FINANCIAL RESERVATION AUDIT =====", flush=True)

        from sqlalchemy import inspect

        columns = {
            c.key: getattr(reservation, c.key)
            for c in inspect(reservation).mapper.column_attrs
        }

        for key, value in sorted(columns.items()):
            if any(term in key for term in (
                "amount", "consumed", "released",
                "reserved", "status"
            )):
                print(
                    f"RESERVATION_{key.upper()}={value}",
                    flush=True,
                )


        assert reservation.reserved_minor == 800
        assert reservation.consumed_minor == 300
        assert reservation.released_minor == 500
        assert reservation.status == "closed"

        assert (
            reservation.reserved_minor
            == reservation.consumed_minor
            + reservation.released_minor
        )

        print("EXACT_RESERVATION_AMOUNTS=PASS", flush=True)
        print("RESERVATION_CONSERVATION=PASS", flush=True)
        print("BILLING_FINALIZATION=PASS", flush=True)
        print("STOP_COMPLETION=PASS", flush=True)
        print("BILLING_GENERATION_FINALIZED=PASS", flush=True)

    with Session(engine, autoflush=False) as db:
        host = db.get(Node, host_id)
        finish_job(
            db,
            node=host,
            job_id=stop_job_id,
            status="succeeded",
            result={},
            error_message="",
        )

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        assert gaming.status == "stopped"
        assert gaming.usage_reservation_id == generation
        print("DUPLICATE_STOP_CALLBACK=PASS", flush=True)


    print("===== FINANCIAL LEDGER AUDIT =====", flush=True)

    with Session(engine, autoflush=False) as db:
        transactions = list(db.scalars(
            select(LedgerTransaction)
        ))

        print(
            f"LEDGER_TRANSACTION_COUNT={len(transactions)}",
            flush=True,
        )

        for transaction in transactions:
            columns = {
                c.key: getattr(transaction, c.key)
                for c in inspect(transaction).mapper.column_attrs
            }
            print(
                "LEDGER_TRANSACTION="
                + repr(columns),
                flush=True,
            )

        entries = list(db.scalars(select(LedgerEntry)))
        print(
            f"LEDGER_ENTRY_COUNT={len(entries)}",
            flush=True,
        )

        for entry in entries:
            columns = {
                c.key: getattr(entry, c.key)
                for c in inspect(entry).mapper.column_attrs
            }
            print(
                "LEDGER_ENTRY="
                + repr(columns),
                flush=True,
            )


    with Session(engine, autoflush=False) as db:
        transactions = list(db.scalars(
            select(LedgerTransaction)
        ))

        generation_transactions = [
            tx for tx in transactions
            if str(generation) in str(tx.idempotency_key or "")
        ]

        charges = [
            tx for tx in generation_transactions
            if tx.transaction_type == "usage_charge"
        ]
        releases = [
            tx for tx in generation_transactions
            if tx.transaction_type == "wallet_reservation_release"
        ]
        extensions = [
            tx for tx in generation_transactions
            if tx.transaction_type == "wallet_reservation_extension"
        ]

        assert len(charges) == 1
        assert len(releases) == 1
        assert len(extensions) == 1

        for tx in generation_transactions:
            assert tx.status == "posted"

            entries = list(db.scalars(
                select(LedgerEntry).where(
                    LedgerEntry.transaction_id == tx.id
                )
            ))

            debits = sum(
                entry.amount_minor
                for entry in entries
                if entry.side == "debit"
            )

            credits = sum(
                entry.amount_minor
                for entry in entries
                if entry.side == "credit"
            )

            assert debits == credits
            assert debits > 0

            if tx.transaction_type == "usage_charge":
                assert debits == 300
            elif tx.transaction_type == "wallet_reservation_release":
                assert debits == 500
            elif tx.transaction_type == "wallet_reservation_extension":
                assert debits == 300

        print("EXACT_LEDGER_TRANSACTION_COUNTS=PASS", flush=True)
        print("DOUBLE_ENTRY_BALANCE=PASS", flush=True)
        print("DUPLICATE_SETTLEMENT_PREVENTION=PASS", flush=True)

    print("FINANCIAL_AUDIT_CAPTURED=PASS", flush=True)
    print("DEFERRED_STOP_LIFECYCLE=PASS", flush=True)



finally:
    engine.dispose()

    with admin_engine.begin() as conn:
        verify(conn)
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))

    admin_engine.dispose()
    print("TEMPORARY_SCHEMA_CLEANUP=PASS", flush=True)
