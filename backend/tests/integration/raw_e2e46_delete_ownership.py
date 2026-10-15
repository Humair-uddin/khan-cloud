"""RAW-E2E-46: isolated PostgreSQL DELETE ownership tests."""
import importlib
import pkgutil
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

import app.models
from app.models.base import Base
from app.models.compute import (
    GamingReservation,
    GamingSession,
    NodeCapacity,
    NodeJob,
)
from app.models.node import Node
from app.models.organization import Organization
from app.models.user import User
from app.services.gaming_service import (
    gaming_delete_ownership_fence,
    gaming_delete_ownership_matches,
)

for module in pkgutil.iter_modules(
    app.models.__path__, prefix="app.models."
):
    importlib.import_module(module.name)

SCHEMA = "raw_e2e46_delete_ownership"
DATA_DIR = (
    "/home/khanadmin/raw-e2e39-recovery/postgres-concurrency"
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
    execution_options={"schema_translate_map": {None: SCHEMA}},
    future=True,
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


def run_tests():
    suffix = uuid4().hex[:12]

    with Session(engine, autoflush=False) as db:
        user = User(
            email=f"delete-{suffix}@example.invalid",
            username=f"delete-{suffix}",
            full_name="DELETE Test",
            password_hash="test-only",
            is_active=True,
        )
        db.add(user)
        db.flush()

        org = Organization(
            name=f"DELETE {suffix}",
            slug=f"delete-{suffix}",
            created_by_user_id=user.id,
            is_active=True,
        )
        db.add(org)
        db.flush()

        node = Node(
            name=f"delete-host-{suffix}",
            machine_id=f"delete-host-{suffix}",
            hostname=f"delete-host-{suffix}",
            secret_hash="test-only",
            intended_purpose="gaming_host",
            lifecycle_state="approved",
            is_enabled=True,
            gaming_accepting_work=True,
        )
        db.add(node)
        db.flush()

        db.add(NodeCapacity(node_id=node.id))

        gaming = GamingSession(
            organization_id=org.id,
            created_by_user_id=user.id,
            name=f"DELETE Gaming {suffix}",
            node_id=node.id,
            gpu_uuid="TEST-GPU-46",
            runtime_id="TEST-RUNTIME-46",
            status="terminating",
            desired_state="terminated",
        )
        db.add(gaming)
        db.flush()

        reservation = GamingReservation(
            gaming_session_id=gaming.id,
            node_id=node.id,
            gpu_uuid=gaming.gpu_uuid,
            cpu=2,
            memory_bytes=4 * 1024**3,
            storage_bytes=20 * 1024**3,
            status="active",
        )
        db.add(reservation)
        db.flush()

        payload = {
            "session_id": str(gaming.id),
            "gpu_uuid": gaming.gpu_uuid,
            **gaming_delete_ownership_fence(db, gaming),
        }

        job = NodeJob(
            node_id=node.id,
            gaming_session_id=gaming.id,
            job_type="gaming.session.delete",
            payload=payload,
            status="pending",
        )
        db.add(job)
        db.flush()

        assert gaming_delete_ownership_matches(
            db, session=gaming, job=job
        )
        print("VALID_DELETE_OWNERSHIP=PASS")

        original = dict(job.payload)

        job.payload = {
            **original,
            "delete_ownership_fence": {
                **original["delete_ownership_fence"],
                "reservation_id": str(uuid4()),
            },
        }
        assert not gaming_delete_ownership_matches(
            db, session=gaming, job=job
        )
        print("STALE_RESERVATION_REJECTED=PASS")

        job.payload = {
            **original,
            "delete_ownership_fence": {
                **original["delete_ownership_fence"],
                "runtime_id": "STALE-RUNTIME",
            },
        }
        assert not gaming_delete_ownership_matches(
            db, session=gaming, job=job
        )
        print("STALE_RUNTIME_REJECTED=PASS")

        job.payload = {
            **original,
            "delete_ownership_fence": {
                **original["delete_ownership_fence"],
                "billing_generation": str(uuid4()),
            },
        }
        assert not gaming_delete_ownership_matches(
            db, session=gaming, job=job
        )
        print("STALE_BILLING_GENERATION_REJECTED=PASS")

        job.payload = {
            "session_id": str(gaming.id),
            "gpu_uuid": gaming.gpu_uuid,
        }
        assert not gaming_delete_ownership_matches(
            db, session=gaming, job=job
        )
        print("UNFENCED_DELETE_REJECTED=PASS")

        job.payload = original
        reservation.status = "released"
        db.flush()

        assert not gaming_delete_ownership_matches(
            db, session=gaming, job=job
        )
        print("RELEASED_RESERVATION_REJECTED=PASS")

        db.rollback()



def test_delete_callbacks():
    """Exercise real callback reconciliation against isolated PostgreSQL."""
    from app.services.compute_service import finish_job

    suffix = uuid4().hex[:12]

    with Session(engine, autoflush=False) as db:
        user = User(
            email=f"callback-{suffix}@example.invalid",
            username=f"callback-{suffix}",
            full_name="Callback Test",
            password_hash="test-only",
            is_active=True,
        )
        db.add(user)
        db.flush()

        org = Organization(
            name=f"Callback {suffix}",
            slug=f"callback-{suffix}",
            created_by_user_id=user.id,
            is_active=True,
        )
        db.add(org)
        db.flush()

        node = Node(
            name=f"callback-host-{suffix}",
            machine_id=f"callback-host-{suffix}",
            hostname=f"callback-host-{suffix}",
            secret_hash="test-only",
            intended_purpose="gaming_host",
            lifecycle_state="approved",
            is_enabled=True,
            gaming_accepting_work=True,
        )
        db.add(node)
        db.flush()

        capacity = NodeCapacity(
            node_id=node.id,
            cpu_allocated=2,
            memory_allocated_bytes=4 * 1024**3,
            storage_allocated_bytes=20 * 1024**3,
        )
        db.add(capacity)

        gaming = GamingSession(
            organization_id=org.id,
            created_by_user_id=user.id,
            name=f"Callback Gaming {suffix}",
            node_id=node.id,
            gpu_uuid="CALLBACK-GPU-46",
            runtime_id="CALLBACK-RUNTIME-46",
            status="terminating",
            desired_state="terminated",
        )
        db.add(gaming)
        db.flush()

        reservation = GamingReservation(
            gaming_session_id=gaming.id,
            node_id=node.id,
            gpu_uuid=gaming.gpu_uuid,
            cpu=2,
            memory_bytes=4 * 1024**3,
            storage_bytes=20 * 1024**3,
            status="active",
        )
        db.add(reservation)
        db.flush()

        payload = {
            "session_id": str(gaming.id),
            "gpu_uuid": gaming.gpu_uuid,
            **gaming_delete_ownership_fence(db, gaming),
        }

        job = NodeJob(
            node_id=node.id,
            gaming_session_id=gaming.id,
            job_type="gaming.session.delete",
            payload=payload,
            status="pending",
        )
        db.add(job)
        db.commit()

        node_id = node.id
        gaming_id = gaming.id
        job_id = job.id

    # A failed DELETE cannot release GPU ownership or capacity.
    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db,
            node=node,
            job_id=job_id,
            status="failed",
            result={},
            error_message="Test sanitization failure",
        )

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        reservation = db.query(GamingReservation).filter_by(
            gaming_session_id=gaming_id
        ).one()
        capacity = db.query(NodeCapacity).filter_by(
            node_id=node_id
        ).one()

        assert reservation.status == "active"
        assert gaming.status != "terminated"
        assert capacity.cpu_allocated == 2
        assert capacity.memory_allocated_bytes == 4 * 1024**3
        assert capacity.storage_allocated_bytes == 20 * 1024**3
        print("FAILED_DELETE_CAPACITY_RETAINED=PASS")

    # Duplicate completion cannot mutate the session or release capacity.
    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db,
            node=node,
            job_id=job_id,
            status="succeeded",
            result={"sanitization": {"sanitized": True}},
            error_message="",
        )

    with Session(engine, autoflush=False) as db:
        reservation = db.query(GamingReservation).filter_by(
            gaming_session_id=gaming_id
        ).one()
        capacity = db.query(NodeCapacity).filter_by(
            node_id=node_id
        ).one()

        assert reservation.status == "active"
        assert capacity.cpu_allocated == 2
        print("DUPLICATE_DELETE_NO_RELEASE=PASS")

    # A stale ownership fence must not alter commercial state.
    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        stale_payload = {
            "session_id": str(gaming.id),
            "gpu_uuid": gaming.gpu_uuid,
            **gaming_delete_ownership_fence(db, gaming),
        }
        stale_payload["delete_ownership_fence"]["runtime_id"] = "OLD-RUNTIME"

        stale_job = NodeJob(
            node_id=node_id,
            gaming_session_id=gaming_id,
            job_type="gaming.session.delete",
            payload=stale_payload,
            status="pending",
        )
        db.add(stale_job)
        db.commit()
        stale_job_id = stale_job.id

    with Session(engine, autoflush=False) as db:
        node = db.get(Node, node_id)
        finish_job(
            db,
            node=node,
            job_id=stale_job_id,
            status="succeeded",
            result={"sanitization": {"sanitized": True}},
            error_message="",
        )

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        reservation = db.query(GamingReservation).filter_by(
            gaming_session_id=gaming_id
        ).one()
        capacity = db.query(NodeCapacity).filter_by(
            node_id=node_id
        ).one()

        assert gaming.status != "terminated"
        assert reservation.status == "active"
        assert capacity.cpu_allocated == 2
        print("STALE_DELETE_CALLBACK_NO_RELEASE=PASS")



def test_delete_success_and_quarantine():
    """Real DELETE callback: proof failure holds capacity; valid proof releases."""
    from app.services.compute_service import finish_job
    from app.services import gaming_service

    original_readiness = gaming_service.gaming_host_readiness_reasons

    # Readiness is isolated here to test the DELETE reconciliation contract.
    # Production readiness behavior is covered by its existing regression tests.
    gaming_service.gaming_host_readiness_reasons = lambda node, now: []

    try:
        for valid_proof in (False, True):
            suffix = uuid4().hex[:12]

            with Session(engine, autoflush=False) as db:
                user = User(
                    email=f"delete-{suffix}@example.invalid",
                    username=f"delete-{suffix}",
                    full_name="DELETE Test",
                    password_hash="test-only",
                    is_active=True,
                )
                db.add(user)
                db.flush()

                org = Organization(
                    name=f"DELETE {suffix}",
                    slug=f"delete-{suffix}",
                    created_by_user_id=user.id,
                    is_active=True,
                )
                db.add(org)
                db.flush()

                node = Node(
                    name=f"delete-host-{suffix}",
                    machine_id=f"delete-host-{suffix}",
                    hostname=f"delete-host-{suffix}",
                    secret_hash="test-only",
                    intended_purpose="gaming_host",
                    lifecycle_state="approved",
                    is_enabled=True,
                    gaming_accepting_work=True,
                )
                db.add(node)
                db.flush()

                db.add(NodeCapacity(
                    node_id=node.id,
                    cpu_allocated=4,
                    memory_allocated_bytes=8 * 1024**3,
                    storage_allocated_bytes=40 * 1024**3,
                ))

                gaming = GamingSession(
                    organization_id=org.id,
                    created_by_user_id=user.id,
                    name=f"DELETE Gaming {suffix}",
                    node_id=node.id,
                    gpu_uuid=f"DELETE-GPU-{suffix}",
                    runtime_id=f"DELETE-RUNTIME-{suffix}",
                    status="terminating",
                    desired_state="terminated",
                )
                db.add(gaming)
                db.flush()

                reservation = GamingReservation(
                    gaming_session_id=gaming.id,
                    node_id=node.id,
                    gpu_uuid=gaming.gpu_uuid,
                    cpu=2,
                    memory_bytes=4 * 1024**3,
                    storage_bytes=20 * 1024**3,
                    status="active",
                )
                db.add(reservation)
                db.flush()

                job = NodeJob(
                    node_id=node.id,
                    gaming_session_id=gaming.id,
                    job_type="gaming.session.delete",
                    payload={
                        "session_id": str(gaming.id),
                        "gpu_uuid": gaming.gpu_uuid,
                        **gaming_delete_ownership_fence(db, gaming),
                    },
                    status="pending",
                )
                db.add(job)
                db.commit()

                node_id = node.id
                gaming_id = gaming.id
                job_id = job.id

            sanitation = {
                "sanitized": valid_proof,
                "runtime_state_deleted": valid_proof,
                "paired_clients_remaining": 0,
                "recorded_launcher_alive": False,
                "ownership_schema_version": 2,
                "runtime_ownership": {
                    "ownership_boundary_verified": valid_proof,
                    "termination_verified": valid_proof,
                    "owned_process_count_remaining": 0,
                },
            }

            with Session(engine, autoflush=False) as db:
                finish_job(
                    db,
                    node=db.get(Node, node_id),
                    job_id=job_id,
                    status="succeeded",
                    result={"sanitization": sanitation},
                    error_message="",
                )

            with Session(engine, autoflush=False) as db:
                gaming = db.get(GamingSession, gaming_id)
                reservation = db.query(GamingReservation).filter_by(
                    gaming_session_id=gaming_id
                ).one()
                capacity = db.query(NodeCapacity).filter_by(
                    node_id=node_id
                ).one()

                if valid_proof:
                    assert gaming.status == "terminated"
                    assert gaming.sanitization_state == "sanitized"
                    assert reservation.status == "released"
                    assert capacity.cpu_allocated == 2
                    assert capacity.memory_allocated_bytes == 4 * 1024**3
                    assert capacity.storage_allocated_bytes == 20 * 1024**3
                    print("VALID_DELETE_EXACT_CAPACITY_RELEASE=PASS")
                else:
                    assert gaming.status == "quarantined"
                    assert gaming.sanitization_state == "quarantined"
                    assert reservation.status == "active"
                    assert capacity.cpu_allocated == 4
                    assert capacity.memory_allocated_bytes == 8 * 1024**3
                    assert capacity.storage_allocated_bytes == 40 * 1024**3
                    print("UNPROVEN_DELETE_QUARANTINE=PASS")

            # Duplicate completion must not release capacity again.
            with Session(engine, autoflush=False) as db:
                finish_job(
                    db,
                    node=db.get(Node, node_id),
                    job_id=job_id,
                    status="succeeded",
                    result={"sanitization": sanitation},
                    error_message="",
                )

            with Session(engine, autoflush=False) as db:
                capacity = db.query(NodeCapacity).filter_by(
                    node_id=node_id
                ).one()
                assert capacity.cpu_allocated == (2 if valid_proof else 4)
                print(
                    "SUCCESS_DUPLICATE_NO_DOUBLE_RELEASE=PASS"
                    if valid_proof
                    else "QUARANTINE_DUPLICATE_NO_RELEASE=PASS"
                )
    finally:
        gaming_service.gaming_host_readiness_reasons = original_readiness



def test_funded_delete_settlement():
    """Funded DELETE closes billing once; failed proof retains GPU capacity."""
    from datetime import UTC, datetime
    from sqlalchemy import func, select
    from app.models.commercial import ProductCatalogItem, ProductSKU
    from app.models.finance import (
        UsageReservation, LedgerTransaction, LedgerEntry,
    )
    from app.services.billing_service import ledger_authoritative_topup
    from app.services.wallet_service import (
        reserve_funds, wallet_balances,
    )
    from app.services.compute_service import finish_job
    from app.services import gaming_service

    original_readiness = gaming_service.gaming_host_readiness_reasons
    gaming_service.gaming_host_readiness_reasons = lambda node, now: []

    try:
        for valid_proof in (False, True):
            suffix = uuid4().hex[:12]

            with Session(engine, autoflush=False) as db:
                user = User(
                    email=f"funded-delete-{suffix}@example.invalid",
                    username=f"funded-delete-{suffix}",
                    full_name="Funded DELETE Test",
                    password_hash="test-only",
                    is_active=True,
                )
                db.add(user)
                db.flush()

                org = Organization(
                    name=f"Funded DELETE {suffix}",
                    slug=f"funded-delete-{suffix}",
                    created_by_user_id=user.id,
                    is_active=True,
                )
                db.add(org)
                db.flush()

                node = Node(
                    name=f"funded-delete-{suffix}",
                    machine_id=f"funded-delete-{suffix}",
                    hostname=f"funded-delete-{suffix}",
                    secret_hash="test-only",
                    intended_purpose="gaming_host",
                    lifecycle_state="approved",
                    is_enabled=True,
                    gaming_accepting_work=True,
                )
                db.add(node)
                db.flush()

                capacity = NodeCapacity(
                    node_id=node.id,
                    cpu_allocated=4,
                    memory_allocated_bytes=8 * 1024**3,
                    storage_allocated_bytes=40 * 1024**3,
                )
                db.add(capacity)

                product = ProductCatalogItem(
                    code=f"funded-delete-{suffix}",
                    workload_type="gaming",
                    name="Funded DELETE Test",
                    currency="USD",
                    is_active=True,
                    is_sellable=True,
                )
                db.add(product)
                db.flush()

                sku = ProductSKU(
                    product_id=product.id,
                    code=f"funded-delete-sku-{suffix}",
                    name="Funded DELETE SKU",
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
                    provider="raw_e2e46_test",
                    provider_reference=f"delete:{suffix}:deposit",
                )

                usage = reserve_funds(
                    db,
                    wallet=wallet,
                    amount_minor=2000,
                    idempotency_key=f"delete:{suffix}:reserve",
                    reference_type="gaming_session",
                    reference_id=f"delete:{suffix}",
                )

                gaming = GamingSession(
                    organization_id=org.id,
                    created_by_user_id=user.id,
                    name=f"Funded DELETE {suffix}",
                    node_id=node.id,
                    gpu_uuid=f"DELETE-GPU-{suffix}",
                    runtime_id=f"DELETE-RUNTIME-{suffix}",
                    product_sku_id=sku.id,
                    usage_reservation_id=usage.id,
                    billing_currency="USD",
                    per_minute_price_minor=100,
                    status="terminating",
                    desired_state="terminated",
                )
                db.add(gaming)
                db.flush()

                reservation = GamingReservation(
                    gaming_session_id=gaming.id,
                    node_id=node.id,
                    gpu_uuid=gaming.gpu_uuid,
                    cpu=2,
                    memory_bytes=4 * 1024**3,
                    storage_bytes=20 * 1024**3,
                    status="active",
                )
                db.add(reservation)
                db.flush()

                job = NodeJob(
                    node_id=node.id,
                    gaming_session_id=gaming.id,
                    job_type="gaming.session.delete",
                    status="pending",
                    payload={
                        "session_id": str(gaming.id),
                        "gpu_uuid": gaming.gpu_uuid,
                        **gaming_delete_ownership_fence(db, gaming),
                    },
                )
                db.add(job)
                db.commit()

                node_id = node.id
                gaming_id = gaming.id
                job_id = job.id
                usage_id = usage.id
                wallet_id = wallet.id

            def snapshot():
                with Session(engine, autoflush=False) as db:
                    gaming = db.get(GamingSession, gaming_id)
                    usage = db.get(UsageReservation, usage_id)
                    wallet = db.get(
                        __import__(
                            "app.models.finance",
                            fromlist=["CustomerWallet"],
                        ).CustomerWallet,
                        wallet_id,
                    )
                    reservation = db.scalar(
                        select(GamingReservation).where(
                            GamingReservation.gaming_session_id == gaming_id
                        )
                    )
                    capacity = db.scalar(
                        select(NodeCapacity).where(
                            NodeCapacity.node_id == node_id
                        )
                    )

                    def count(model):
                        return db.scalar(
                            select(func.count()).select_from(model)
                        )

                    return {
                        "wallet": wallet_balances(db, wallet),
                        "transactions": count(LedgerTransaction),
                        "entries": count(LedgerEntry),
                        "usage_status": usage.status,
                        "reserved": usage.reserved_minor,
                        "consumed": usage.consumed_minor,
                        "released": usage.released_minor,
                        "gpu_status": reservation.status,
                        "cpu": capacity.cpu_allocated,
                        "memory": capacity.memory_allocated_bytes,
                        "storage": capacity.storage_allocated_bytes,
                        "session_status": gaming.status,
                        "billing_finalized_at": gaming.billing_finalized_at,
                    }

            before = snapshot()
            assert before["usage_status"] == "reserved"
            assert before["reserved"] == 2000
            assert before["consumed"] == 0
            assert before["released"] == 0
            assert before["wallet"]["reserved_minor"] == 2000

            sanitation = {
                "sanitized": valid_proof,
                "runtime_state_deleted": valid_proof,
                "paired_clients_remaining": 0,
                "recorded_launcher_alive": False,
                "ownership_schema_version": 2,
                "runtime_ownership": {
                    "ownership_boundary_verified": valid_proof,
                    "termination_verified": valid_proof,
                    "owned_process_count_remaining": 0,
                },
            }

            with Session(engine, autoflush=False) as db:
                finish_job(
                    db,
                    node=db.get(Node, node_id),
                    job_id=job_id,
                    status="succeeded",
                    result={"sanitization": sanitation},
                    error_message="",
                )

            after = snapshot()

            assert after["billing_finalized_at"] is not None
            assert after["usage_status"] == "closed"
            assert after["reserved"] == 2000
            assert after["consumed"] == 0
            assert after["released"] == 2000
            assert after["wallet"]["reserved_minor"] == 0
            assert (
                after["wallet"]["available_minor"]
                == before["wallet"]["available_minor"] + 2000
            )
            assert after["transactions"] == before["transactions"] + 1
            assert after["entries"] == before["entries"] + 2

            print(
                "FUNDED_DELETE_SETTLEMENT=PASS"
                if valid_proof
                else "FUNDED_QUARANTINE_SETTLEMENT=PASS",
                flush=True,
            )

            if valid_proof:
                assert after["session_status"] == "terminated"
                assert after["gpu_status"] == "released"
                assert after["cpu"] == 2
                assert after["memory"] == 4 * 1024**3
                assert after["storage"] == 20 * 1024**3
                print("FUNDED_DELETE_CAPACITY_RELEASE=PASS", flush=True)
            else:
                assert after["session_status"] == "quarantined"
                assert after["gpu_status"] == "active"
                assert after["cpu"] == 4
                assert after["memory"] == 8 * 1024**3
                assert after["storage"] == 40 * 1024**3
                print("FUNDED_QUARANTINE_CAPACITY_RETAINED=PASS", flush=True)

            with Session(engine, autoflush=False) as db:
                finish_job(
                    db,
                    node=db.get(Node, node_id),
                    job_id=job_id,
                    status="succeeded",
                    result={"sanitization": sanitation},
                    error_message="",
                )

            duplicate = snapshot()
            assert duplicate == after, (after, duplicate)
            print("FUNDED_DELETE_DUPLICATE_IDEMPOTENT=PASS", flush=True)

            if not valid_proof:
                from app.services.gaming_service import (
                    queue_gaming_quarantine_recovery,
                )

                with Session(engine, autoflush=False) as db:
                    gaming = db.get(GamingSession, gaming_id)
                    assert gaming.status == "quarantined"
                    queue_gaming_quarantine_recovery(
                        db,
                        session=gaming,
                        source="operator",
                        actor_user_id=gaming.created_by_user_id,
                        reason="funded recovery ledger qualification",
                        commit=False,
                    )
                    db.commit()

                    recovery = db.scalar(
                        select(NodeJob).where(
                            NodeJob.gaming_session_id == gaming_id,
                            NodeJob.job_type == "gaming.session.delete",
                            NodeJob.status == "pending",
                        )
                    )
                    assert recovery is not None
                    assert recovery.payload["quarantine_recovery"] is True
                    recovery_id = recovery.id

                before_recovery = snapshot()

                recovery_proof = {
                    "sanitized": True,
                    "runtime_state_deleted": True,
                    "paired_clients_remaining": 0,
                    "recorded_launcher_alive": False,
                    "ownership_schema_version": 2,
                    "runtime_ownership": {
                        "ownership_boundary_verified": True,
                        "termination_verified": True,
                        "owned_process_count_remaining": 0,
                    },
                }

                with Session(engine, autoflush=False) as db:
                    finish_job(
                        db,
                        node=db.get(Node, node_id),
                        job_id=recovery_id,
                        status="succeeded",
                        result={"sanitization": recovery_proof},
                        error_message="",
                    )

                after_recovery = snapshot()

                for key in (
                    "wallet",
                    "transactions",
                    "entries",
                    "usage_status",
                    "reserved",
                    "consumed",
                    "released",
                    "billing_finalized_at",
                ):
                    assert after_recovery[key] == before_recovery[key], (
                        key, before_recovery[key], after_recovery[key]
                    )

                assert after_recovery["session_status"] == "terminated"
                assert after_recovery["gpu_status"] == "released"
                assert after_recovery["cpu"] == 2
                assert after_recovery["memory"] == 4 * 1024**3
                assert after_recovery["storage"] == 20 * 1024**3

                print("FUNDED_RECOVERY_LEDGER_UNCHANGED=PASS", flush=True)
                print("FUNDED_RECOVERY_CAPACITY_RELEASE=PASS", flush=True)

                with Session(engine, autoflush=False) as db:
                    finish_job(
                        db,
                        node=db.get(Node, node_id),
                        job_id=recovery_id,
                        status="succeeded",
                        result={"sanitization": recovery_proof},
                        error_message="",
                    )

                assert snapshot() == after_recovery
                print("FUNDED_RECOVERY_DUPLICATE_IDEMPOTENT=PASS", flush=True)

    finally:
        gaming_service.gaming_host_readiness_reasons = original_readiness


def test_recovery_and_vm_delete():
    """Quarantine recovery and VM DELETE retain exact capacity ownership."""
    from sqlalchemy import select
    from app.services.compute_service import finish_job
    from app.services.gaming_service import queue_gaming_quarantine_recovery
    from app.services import gaming_service

    original_readiness = gaming_service.gaming_host_readiness_reasons
    gaming_service.gaming_host_readiness_reasons = lambda node, now: []

    proof = {
        "sanitized": True,
        "runtime_state_deleted": True,
        "paired_clients_remaining": 0,
        "recorded_launcher_alive": False,
        "ownership_schema_version": 2,
        "runtime_ownership": {
            "ownership_boundary_verified": True,
            "termination_verified": True,
            "owned_process_count_remaining": 0,
        },
    }

    try:
        for mode in ("bare_metal", "proxmox_windows_vm"):
            suffix = uuid4().hex[:12]

            with Session(engine, autoflush=False) as db:
                user = User(
                    email=f"recovery-{suffix}@example.invalid",
                    username=f"recovery-{suffix}",
                    full_name="Recovery Test",
                    password_hash="test-only",
                    is_active=True,
                )
                db.add(user)
                db.flush()

                org = Organization(
                    name=f"Recovery {suffix}",
                    slug=f"recovery-{suffix}",
                    created_by_user_id=user.id,
                    is_active=True,
                )
                db.add(org)
                db.flush()

                node = Node(
                    name=f"recovery-host-{suffix}",
                    machine_id=f"recovery-host-{suffix}",
                    hostname=f"recovery-host-{suffix}",
                    secret_hash="test-only",
                    intended_purpose="gaming_host",
                    lifecycle_state="approved",
                    is_enabled=True,
                    gaming_accepting_work=True,
                )
                db.add(node)
                db.flush()

                db.add(NodeCapacity(
                    node_id=node.id,
                    cpu_allocated=4,
                    memory_allocated_bytes=8 * 1024**3,
                    storage_allocated_bytes=40 * 1024**3,
                ))

                gaming = GamingSession(
                    organization_id=org.id,
                    created_by_user_id=user.id,
                    name=f"Recovery {suffix}",
                    node_id=node.id,
                    gpu_uuid=f"RECOVERY-GPU-{suffix}",
                    runtime_id=f"RECOVERY-RUNTIME-{suffix}",
                    deployment_mode=mode,
                    status="terminating",
                    desired_state="terminated",
                )
                db.add(gaming)
                db.flush()

                reservation = GamingReservation(
                    gaming_session_id=gaming.id,
                    node_id=node.id,
                    gpu_uuid=gaming.gpu_uuid,
                    cpu=2,
                    memory_bytes=4 * 1024**3,
                    storage_bytes=20 * 1024**3,
                    status="active",
                )
                db.add(reservation)
                db.flush()

                job = NodeJob(
                    node_id=node.id,
                    gaming_session_id=gaming.id,
                    job_type=(
                        "gaming.session.delete"
                        if mode == "bare_metal"
                        else "gaming.vm.delete"
                    ),
                    status="pending",
                    payload={
                        "session_id": str(gaming.id),
                        "gpu_uuid": gaming.gpu_uuid,
                        **gaming_delete_ownership_fence(db, gaming),
                    },
                )
                db.add(job)
                db.commit()

                node_id = node.id
                gaming_id = gaming.id
                job_id = job.id

            if mode == "bare_metal":
                # First DELETE lacks authoritative sanitization proof.
                with Session(engine, autoflush=False) as db:
                    finish_job(
                        db,
                        node=db.get(Node, node_id),
                        job_id=job_id,
                        status="succeeded",
                        result={"sanitization": {}},
                        error_message="",
                    )

                with Session(engine, autoflush=False) as db:
                    gaming = db.get(GamingSession, gaming_id)
                    assert gaming.status == "quarantined"
                    assert gaming.sanitization_state == "quarantined"

                    queue_gaming_quarantine_recovery(
                        db,
                        session=gaming,
                        source="operator",
                        actor_user_id=gaming.created_by_user_id,
                        reason="isolated recovery qualification",
                        commit=False,
                    )
                    db.commit()

                    recovery = db.scalar(
                        select(NodeJob).where(
                            NodeJob.gaming_session_id == gaming_id,
                            NodeJob.status == "pending",
                            NodeJob.job_type == "gaming.session.delete",
                        )
                    )
                    assert recovery is not None
                    assert recovery.payload["quarantine_recovery"] is True
                    recovery_id = recovery.id

                print("QUARANTINE_RECOVERY_FENCE_QUEUED=PASS", flush=True)

                with Session(engine, autoflush=False) as db:
                    finish_job(
                        db,
                        node=db.get(Node, node_id),
                        job_id=recovery_id,
                        status="succeeded",
                        result={"sanitization": proof},
                        error_message="",
                    )

                with Session(engine, autoflush=False) as db:
                    gaming = db.get(GamingSession, gaming_id)
                    assert gaming.status == "terminated"
                    assert gaming.sanitization_state == "sanitized"
                    assert gaming.quarantine_recovery_state == "recovered"

                print("QUARANTINE_RECOVERY_TERMINATED=PASS", flush=True)

            else:
                with Session(engine, autoflush=False) as db:
                    finish_job(
                        db,
                        node=db.get(Node, node_id),
                        job_id=job_id,
                        status="succeeded",
                        result={},
                        error_message="",
                    )

                print("VM_DELETE_CALLBACK_SUCCEEDED=PASS", flush=True)

            with Session(engine, autoflush=False) as db:
                gaming = db.get(GamingSession, gaming_id)
                reservation = db.scalar(
                    select(GamingReservation).where(
                        GamingReservation.gaming_session_id == gaming_id
                    )
                )
                capacity = db.scalar(
                    select(NodeCapacity).where(
                        NodeCapacity.node_id == node_id
                    )
                )

                assert gaming.status == "terminated"
                assert reservation.status == "released"
                assert capacity.cpu_allocated == 2
                assert capacity.memory_allocated_bytes == 4 * 1024**3
                assert capacity.storage_allocated_bytes == 20 * 1024**3

            print(
                "RECOVERY_EXACT_CAPACITY_RELEASE=PASS"
                if mode == "bare_metal"
                else "VM_EXACT_CAPACITY_RELEASE=PASS",
                flush=True,
            )

            # Duplicate successful completion must never release twice.
            completed_id = (
                recovery_id if mode == "bare_metal" else job_id
            )

            with Session(engine, autoflush=False) as db:
                finish_job(
                    db,
                    node=db.get(Node, node_id),
                    job_id=completed_id,
                    status="succeeded",
                    result=(
                        {"sanitization": proof}
                        if mode == "bare_metal"
                        else {}
                    ),
                    error_message="",
                )

            with Session(engine, autoflush=False) as db:
                capacity = db.scalar(
                    select(NodeCapacity).where(
                        NodeCapacity.node_id == node_id
                    )
                )
                reservation = db.scalar(
                    select(GamingReservation).where(
                        GamingReservation.gaming_session_id == gaming_id
                    )
                )
                assert capacity.cpu_allocated == 2
                assert capacity.memory_allocated_bytes == 4 * 1024**3
                assert capacity.storage_allocated_bytes == 20 * 1024**3
                assert reservation.status == "released"

            print(
                "RECOVERY_DUPLICATE_NO_DOUBLE_RELEASE=PASS"
                if mode == "bare_metal"
                else "VM_DUPLICATE_NO_DOUBLE_RELEASE=PASS",
                flush=True,
            )

    finally:
        gaming_service.gaming_host_readiness_reasons = original_readiness


def test_stale_vm_delete_callback():
    """Stale VM DELETE success cannot terminate or release current ownership."""
    from sqlalchemy import select
    from app.services.compute_service import finish_job

    suffix = uuid4().hex[:12]

    with Session(engine, autoflush=False) as db:
        user = User(
            email=f"stale-vm-{suffix}@example.invalid",
            username=f"stale-vm-{suffix}",
            full_name="Stale VM DELETE",
            password_hash="test-only",
            is_active=True,
        )
        db.add(user)
        db.flush()

        org = Organization(
            name=f"Stale VM {suffix}",
            slug=f"stale-vm-{suffix}",
            created_by_user_id=user.id,
            is_active=True,
        )
        db.add(org)
        db.flush()

        node = Node(
            name=f"stale-vm-{suffix}",
            machine_id=f"stale-vm-{suffix}",
            hostname=f"stale-vm-{suffix}",
            secret_hash="test-only",
            intended_purpose="gaming_host",
            lifecycle_state="approved",
            is_enabled=True,
            gaming_accepting_work=True,
        )
        db.add(node)
        db.flush()

        db.add(NodeCapacity(
            node_id=node.id,
            cpu_allocated=4,
            memory_allocated_bytes=8 * 1024**3,
            storage_allocated_bytes=40 * 1024**3,
        ))

        gaming = GamingSession(
            organization_id=org.id,
            created_by_user_id=user.id,
            name=f"Stale VM {suffix}",
            node_id=node.id,
            gpu_uuid=f"STALE-GPU-{suffix}",
            runtime_id=f"CURRENT-RUNTIME-{suffix}",
            deployment_mode="proxmox_windows_vm",
            status="terminating",
            desired_state="terminated",
        )
        db.add(gaming)
        db.flush()

        reservation = GamingReservation(
            gaming_session_id=gaming.id,
            node_id=node.id,
            gpu_uuid=gaming.gpu_uuid,
            cpu=2,
            memory_bytes=4 * 1024**3,
            storage_bytes=20 * 1024**3,
            status="active",
        )
        db.add(reservation)
        db.flush()

        fence = gaming_delete_ownership_fence(db, gaming)
        fence["delete_ownership_fence"]["runtime_id"] = "OLD-RUNTIME"

        job = NodeJob(
            node_id=node.id,
            gaming_session_id=gaming.id,
            job_type="gaming.vm.delete",
            status="pending",
            payload={
                "session_id": str(gaming.id),
                "gpu_uuid": gaming.gpu_uuid,
                **fence,
            },
        )
        db.add(job)
        db.commit()

        node_id = node.id
        gaming_id = gaming.id
        job_id = job.id

    with Session(engine, autoflush=False) as db:
        finish_job(
            db,
            node=db.get(Node, node_id),
            job_id=job_id,
            status="succeeded",
            result={},
            error_message="",
        )

    with Session(engine, autoflush=False) as db:
        gaming = db.get(GamingSession, gaming_id)
        reservation = db.scalar(
            select(GamingReservation).where(
                GamingReservation.gaming_session_id == gaming_id
            )
        )
        capacity = db.scalar(
            select(NodeCapacity).where(
                NodeCapacity.node_id == node_id
            )
        )

        assert gaming.status == "terminating"
        assert gaming.runtime_id == f"CURRENT-RUNTIME-{suffix}"
        assert reservation.status == "active"
        assert capacity.cpu_allocated == 4
        assert capacity.memory_allocated_bytes == 8 * 1024**3
        assert capacity.storage_allocated_bytes == 40 * 1024**3

    print("STALE_VM_DELETE_CALLBACK_REJECTED=PASS", flush=True)

def main():
    with admin.connect() as conn:
        verify(conn)

    with admin.begin() as conn:
        verify(conn)
        exists = conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_namespace
                    WHERE nspname = :schema
                )
            """),
            {"schema": SCHEMA},
        ).scalar_one()
        assert not exists, "Temporary schema already exists"
        conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))

    print("ISOLATED_SCHEMA=PASS")

    try:
        with engine.begin() as conn:
            Base.metadata.create_all(conn)
        run_tests()
        print("RAW_E2E46M_OWNERSHIP=PASS")
        test_delete_callbacks()
        print("RAW_E2E46P_CALLBACKS=PASS")
        test_delete_success_and_quarantine()
        print("RAW_E2E46S_DELETE=PASS")
        test_funded_delete_settlement()
        print("RAW_E2E46X_FUNDED_DELETE=PASS")
        test_recovery_and_vm_delete()
        print("RAW_E2E46Z_RECOVERY_VM=PASS")
        print("RAW_E2E46AB_DUPLICATE_CALLBACKS=PASS")
        test_stale_vm_delete_callback()
        print("RAW_E2E46AC_STALE_VM=PASS")
        print("RAW_E2E46AD_FINANCIAL_RECOVERY=PASS")
    finally:
        with admin.begin() as conn:
            verify(conn)
            conn.execute(
                text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE')
            )
        print("TEMPORARY_SCHEMA_CLEANED=PASS")


if __name__ == "__main__":
    main()
