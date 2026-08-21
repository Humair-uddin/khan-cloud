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
ACTIVE_CONNECTION_JOB_STATES = {"pending", "running"}
NON_PAIRED_INVALIDATABLE_STATES = {
    "pending",
    "pairing",
    "failed",
    "expired",
}


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
        node_id=(session.guest_node_id or session.node_id),
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
            NodeJob.status.in_(ACTIVE_CONNECTION_JOB_STATES),
            NodeJob.payload["lease_id"].astext
            == str(lease.id),
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
            NodeJob.status.in_(ACTIVE_CONNECTION_JOB_STATES),
            NodeJob.payload["lease_id"].astext
            == str(lease.id),
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


def prepare_connection_shutdown(
    db: Session,
    *,
    session: GamingSession,
) -> bool:
    """Prepare every connection lease before runtime shutdown.

    Returns True when runtime stop/delete may proceed immediately.
    Returns False when at least one Sunshine revocation must complete first.
    """

    leases = list(
        db.scalars(
            select(GamingConnectionLease)
            .where(
                GamingConnectionLease.gaming_session_id == session.id,
                GamingConnectionLease.state.in_(
                    {
                        "pending",
                        "pairing",
                        "paired",
                        "revoking",
                        "failed",
                        "expired",
                    }
                ),
            )
            .order_by(GamingConnectionLease.created_at)
        )
    )

    waiting = False
    now = _now()

    for lease in leases:
        if lease.state == "paired":
            if not lease.sunshine_client_uuid:
                lease.state = "failed"
                lease.failure_message = (
                    "Paired connection is missing its Sunshine "
                    "client identity during session shutdown."
                )
                continue

            pending = db.scalar(
                select(NodeJob)
                .where(
                    NodeJob.gaming_session_id == session.id,
                    NodeJob.job_type == "gaming.connection.revoke",
                    NodeJob.status.in_(ACTIVE_CONNECTION_JOB_STATES),
                    NodeJob.payload["lease_id"].astext
                    == str(lease.id),
                )
                .limit(1)
            )

            if pending is None:
                lease.state = "revoking"
                lease.failure_message = ""
                db.add(
                    NodeJob(
                        node_id=lease.node_id,
                        gaming_session_id=session.id,
                        job_type="gaming.connection.revoke",
                        payload={
                            "session_id": str(session.id),
                            "lease_id": str(lease.id),
                            "sunshine_client_uuid":
                                lease.sunshine_client_uuid,
                            "automatic_shutdown": True,
                        },
                    )
                )

            waiting = True
            continue

        if lease.state == "revoking":
            waiting = True
            continue

        if lease.state in NON_PAIRED_INVALIDATABLE_STATES:
            lease.state = "revoked"
            lease.revoked_at = now
            lease.failure_message = ""

    return not waiting


def continue_deferred_session_action(
    db: Session,
    *,
    session: GamingSession,
) -> None:
    """Continue stop/delete after all connection teardown is complete."""

    if session.desired_state not in {"stopped", "terminated"}:
        return

    blocking = db.scalar(
        select(GamingConnectionLease)
        .where(
            GamingConnectionLease.gaming_session_id == session.id,
            GamingConnectionLease.state.in_({"paired", "revoking"}),
        )
        .limit(1)
    )

    if blocking is not None:
        return

    pending_session_job = db.scalar(
        select(NodeJob)
        .where(
            NodeJob.gaming_session_id == session.id,
            NodeJob.job_type.in_(
                {
                    "gaming.session.stop",
                    "gaming.session.delete",
                }
            ),
            NodeJob.status.in_(ACTIVE_CONNECTION_JOB_STATES),
        )
        .limit(1)
    )

    if pending_session_job is not None:
        return

    if session.node_id is None:
        session.status = "error"
        session.failure_category = "missing_node"
        session.failure_message = (
            "Gaming session lost its assigned node during shutdown."
        )
        return

    action = (
        "delete"
        if session.desired_state == "terminated"
        else "stop"
    )

    session.status = (
        "terminating"
        if action == "delete"
        else "stopping"
    )

    job_type = (
        f"gaming.vm.{action}"
        if session.deployment_mode == "proxmox_windows_vm"
        else f"gaming.session.{action}"
    )
    db.add(
        NodeJob(
            node_id=session.node_id,
            gaming_session_id=session.id,
            job_type=job_type,
            payload={
                "session_id": str(session.id),
                "gpu_uuid": session.gpu_uuid,
            },
        )
    )


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

    if job.job_type == "gaming.connection.pair":
        # A late pairing result must never resurrect an invalidated,
        # revoked, or otherwise superseded lease.
        if lease.state != "pairing":
            return

        if status != "succeeded":
            lease.state = "failed"
            lease.failure_message = error_message[:500]
            return

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
        return

    if job.job_type == "gaming.connection.revoke":
        # Likewise, only the revocation operation that owns the
        # current revoking state may reconcile it.
        if lease.state != "revoking":
            return

        session = db.get(
            GamingSession,
            lease.gaming_session_id,
        )

        if status != "succeeded":
            lease.state = "failed"
            lease.failure_message = error_message[:500]

            if (
                session is not None
                and session.desired_state
                in {"stopped", "terminated"}
            ):
                session.status = "error"
                session.failure_category = (
                    "connection_revocation_failed"
                )
                session.failure_message = (
                    "Secure gaming connection revocation failed; "
                    "runtime shutdown was not attempted."
                )
            return

        lease.state = "revoked"
        lease.revoked_at = _now()
        lease.failure_message = ""

        if session is not None:
            continue_deferred_session_action(
                db,
                session=session,
            )
