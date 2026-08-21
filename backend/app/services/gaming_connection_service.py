from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compute import (
    GamingConnectionLease,
    GamingSession,
    NodeJob,
)
from app.models.user import User
from app.services.compute_service import ComputeError
from app.services.gaming_service import get_visible_gaming_session


PAIRABLE_STATES = {"pending", "failed"}
ACTIVE_PAIRING_JOB_STATES = {"pending", "running"}


def _now() -> datetime:
    return datetime.now(UTC)


def create_connection_lease(
    db: Session,
    *,
    session: GamingSession,
    actor: User,
    pairing_ttl_seconds: int,
) -> GamingConnectionLease:
    if session.status != "running":
        raise ComputeError(
            "Gaming connection leases require a running session."
        )

    if session.node_id is None:
        raise ComputeError(
            "Gaming session has no assigned node."
        )

    existing = db.scalar(
        select(GamingConnectionLease)
        .where(
            GamingConnectionLease.gaming_session_id == session.id,
            GamingConnectionLease.user_id == actor.id,
            GamingConnectionLease.state.in_(
                {"pending", "pairing", "paired"}
            ),
        )
        .order_by(GamingConnectionLease.created_at.desc())
        .limit(1)
    )

    now = _now()

    if existing is not None:
        if existing.state == "paired":
            return existing

        if existing.pairing_expires_at > now:
            return existing

        existing.state = "expired"

    lease = GamingConnectionLease(
        gaming_session_id=session.id,
        organization_id=session.organization_id,
        user_id=actor.id,
        node_id=session.node_id,
        state="pending",
        client_name=(
            f"KC-{str(session.id)[:8]}-"
            f"{secrets.token_hex(4)}"
        ),
        pairing_expires_at=(
            now + timedelta(seconds=pairing_ttl_seconds)
        ),
    )

    db.add(lease)
    db.commit()
    db.refresh(lease)
    return lease


def get_visible_connection_lease(
    db: Session,
    *,
    actor: User,
    session_id: UUID,
    lease_id: UUID,
) -> GamingConnectionLease:
    session = get_visible_gaming_session(
        db,
        actor,
        session_id,
    )

    lease = db.get(GamingConnectionLease, lease_id)

    if (
        lease is None
        or lease.gaming_session_id != session.id
        or lease.organization_id != session.organization_id
    ):
        raise ComputeError("Gaming connection lease not found.")

    return lease


def queue_pairing(
    db: Session,
    *,
    lease: GamingConnectionLease,
    pin: str,
) -> GamingConnectionLease:
    now = _now()

    if lease.state == "paired":
        return lease

    if lease.state not in PAIRABLE_STATES:
        raise ComputeError(
            "Gaming connection lease cannot be paired in its current state."
        )

    if lease.pairing_expires_at <= now:
        lease.state = "expired"
        db.commit()
        raise ComputeError(
            "Gaming connection pairing window has expired."
        )

    pending = db.scalar(
        select(NodeJob)
        .where(
            NodeJob.gaming_session_id
            == lease.gaming_session_id,
            NodeJob.job_type
            == "gaming.connection.pair",
            NodeJob.status.in_(ACTIVE_PAIRING_JOB_STATES),
        )
        .limit(1)
    )

    if pending is not None:
        raise ComputeError(
            "Gaming connection pairing is already in progress."
        )

    lease.state = "pairing"
    lease.failure_message = ""

    # PIN is intentionally short-lived. It is scrubbed from the
    # authoritative job payload as soon as the node reports a result.
    db.add(
        NodeJob(
            node_id=lease.node_id,
            gaming_session_id=lease.gaming_session_id,
            job_type="gaming.connection.pair",
            payload={
                "session_id": str(lease.gaming_session_id),
                "lease_id": str(lease.id),
                "pin": pin,
                "client_name": lease.client_name,
            },
        )
    )

    db.commit()
    db.refresh(lease)
    return lease


def queue_revocation(
    db: Session,
    *,
    lease: GamingConnectionLease,
) -> GamingConnectionLease:
    if lease.state == "revoked":
        return lease

    if lease.state != "paired":
        raise ComputeError(
            "Only a paired gaming connection can be revoked."
        )

    if not lease.sunshine_client_uuid:
        raise ComputeError(
            "Paired connection is missing its Sunshine client identity."
        )

    pending = db.scalar(
        select(NodeJob)
        .where(
            NodeJob.gaming_session_id
            == lease.gaming_session_id,
            NodeJob.job_type
            == "gaming.connection.revoke",
            NodeJob.status.in_(ACTIVE_PAIRING_JOB_STATES),
        )
        .limit(1)
    )

    if pending is not None:
        raise ComputeError(
            "Gaming connection revocation is already in progress."
        )

    lease.state = "revoking"

    db.add(
        NodeJob(
            node_id=lease.node_id,
            gaming_session_id=lease.gaming_session_id,
            job_type="gaming.connection.revoke",
            payload={
                "session_id": str(lease.gaming_session_id),
                "lease_id": str(lease.id),
                "sunshine_client_uuid":
                    lease.sunshine_client_uuid,
            },
        )
    )

    db.commit()
    db.refresh(lease)
    return lease


def finish_connection_job(
    db: Session,
    *,
    job: NodeJob,
    status: str,
    result: dict,
    error_message: str,
) -> None:
    raw_lease_id = str(
        (job.payload or {}).get("lease_id") or ""
    )

    # Never retain a customer pairing PIN after completion.
    job.payload = {
        "lease_id": raw_lease_id,
        "redacted": True,
    }

    try:
        lease_id = UUID(raw_lease_id)
    except (ValueError, TypeError):
        return

    lease = db.get(GamingConnectionLease, lease_id)

    if lease is None:
        return

    if status != "succeeded":
        lease.state = "failed"
        lease.failure_message = error_message[:500]
        return

    if job.job_type == "gaming.connection.pair":
        client_uuid = str(
            result.get("sunshine_client_uuid") or ""
        ).strip()

        if not client_uuid:
            lease.state = "failed"
            lease.failure_message = (
                "Node paired the connection without returning "
                "a Sunshine client UUID."
            )
            return

        lease.state = "paired"
        lease.sunshine_client_uuid = client_uuid
        lease.paired_at = _now()
        lease.failure_message = ""

    elif job.job_type == "gaming.connection.revoke":
        lease.state = "revoked"
        lease.revoked_at = _now()
        lease.failure_message = ""
