from __future__ import annotations

import hashlib
import hmac
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
ACTIVE_LEASE_STATES = {
    "pending",
    "pairing",
    "paired",
    "connected",
    "reconnect_grace",
    "revoking",
}
NON_PAIRED_INVALIDATABLE_STATES = {
    "pending",
    "pairing",
    "failed",
    "expired",
    "reconnect_grace",
}
DEFAULT_RECONNECT_GRACE_SECONDS = 120


def _now() -> datetime:
    return datetime.now(UTC)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _mint_connection_token(lease: GamingConnectionLease, *, ttl_seconds: int) -> str:
    token = secrets.token_urlsafe(48)
    lease.connection_token_hash = _token_hash(token)
    lease.connection_token_expires_at = _now() + timedelta(seconds=ttl_seconds)
    lease.token_generation = int(lease.token_generation or 0) + 1
    return token


def _verify_connection_token(lease: GamingConnectionLease, token: str, *, now: datetime) -> None:
    if not lease.connection_token_hash or lease.connection_token_expires_at is None:
        raise ComputeError("Gaming connection credential is not active.")
    if lease.connection_token_expires_at <= now:
        raise ComputeError("Gaming connection credential has expired.")
    candidate = _token_hash(token)
    if not hmac.compare_digest(candidate, lease.connection_token_hash):
        raise ComputeError("Gaming connection credential is invalid.")


def create_connection_lease(
    db: Session,
    *,
    session: GamingSession,
    actor: User,
    pairing_ttl_seconds: int,
    connection_ttl_seconds: int = 14400,
    reconnect_grace_seconds: int = DEFAULT_RECONNECT_GRACE_SECONDS,
) -> tuple[GamingConnectionLease, str]:
    if session.status != "running":
        raise ComputeError("Gaming connection leases require a running session.")
    if session.node_id is None:
        raise ComputeError("Gaming session has no assigned node.")

    # Serialize lease issuance on the authoritative gaming-session row.
    locked_session = db.scalar(
        select(GamingSession).where(GamingSession.id == session.id).with_for_update()
    )
    if locked_session is None:
        raise ComputeError("Gaming session not found.")

    now = _now()
    existing = db.scalar(
        select(GamingConnectionLease)
        .where(
            GamingConnectionLease.gaming_session_id == session.id,
            GamingConnectionLease.state.in_(ACTIVE_LEASE_STATES),
        )
        .order_by(GamingConnectionLease.created_at.desc())
        .limit(1)
    )

    if existing is not None:
        if existing.user_id != actor.id:
            raise ComputeError("Gaming session already has an active customer connection lease.")
        if existing.state in {"pending", "pairing"} and existing.pairing_expires_at <= now:
            existing.state = "expired"
            existing.revoked_reason = "pairing_expired"
        elif existing.state == "revoking":
            raise ComputeError("Gaming connection lease is being revoked.")
        else:
            # Rotation invalidates any copied/replayed control-plane credential
            # without creating a second Sunshine client or runtime.
            token = _mint_connection_token(existing, ttl_seconds=connection_ttl_seconds)
            existing.reconnect_grace_expires_at = None
            db.commit()
            db.refresh(existing)
            return existing, token

    lease = GamingConnectionLease(
        gaming_session_id=session.id,
        organization_id=session.organization_id,
        user_id=actor.id,
        node_id=(session.guest_node_id or session.node_id),
        state="pending",
        client_name=f"KC-{str(session.id)[:8]}-{secrets.token_hex(4)}",
        pairing_expires_at=now + timedelta(seconds=pairing_ttl_seconds),
        reconnect_grace_seconds=reconnect_grace_seconds,
    )
    # Persist policy with the lease so backend restarts do not change the
    # reconnect contract for an already-issued session.
    lease.reconnect_grace_expires_at = None
    token = _mint_connection_token(lease, ttl_seconds=connection_ttl_seconds)
    lease.failure_message = ""
    db.add(lease)
    db.commit()
    db.refresh(lease)
    return lease, token


def get_visible_connection_lease(
    db: Session, *, actor: User, session_id: UUID, lease_id: UUID
) -> GamingConnectionLease:
    session = get_visible_gaming_session(db, actor, session_id)
    lease = db.get(GamingConnectionLease, lease_id)
    if (
        lease is None
        or lease.gaming_session_id != session.id
        or lease.organization_id != session.organization_id
    ):
        raise ComputeError("Gaming connection lease not found.")
    return lease


def queue_pairing(db: Session, *, lease: GamingConnectionLease, pin: str) -> GamingConnectionLease:
    now = _now()
    if lease.state in {"paired", "connected", "reconnect_grace"}:
        return lease
    if lease.state not in PAIRABLE_STATES:
        raise ComputeError("Gaming connection lease cannot be paired in its current state.")
    if lease.pairing_expires_at <= now:
        lease.state = "expired"
        lease.revoked_reason = "pairing_expired"
        db.commit()
        raise ComputeError("Gaming connection pairing window has expired.")
    pending = db.scalar(
        select(NodeJob).where(
            NodeJob.gaming_session_id == lease.gaming_session_id,
            NodeJob.job_type == "gaming.connection.pair",
            NodeJob.status.in_(ACTIVE_CONNECTION_JOB_STATES),
            NodeJob.payload["lease_id"].astext == str(lease.id),
        ).limit(1)
    )
    if pending is not None:
        raise ComputeError("Gaming connection pairing is already in progress.")
    lease.state = "pairing"
    lease.failure_message = ""
    db.add(NodeJob(
        node_id=lease.node_id,
        gaming_session_id=lease.gaming_session_id,
        job_type="gaming.connection.pair",
        payload={
            "session_id": str(lease.gaming_session_id),
            "lease_id": str(lease.id),
            "pin": pin,
            "client_name": lease.client_name,
        },
    ))
    db.commit(); db.refresh(lease)
    return lease


def queue_revocation(
    db: Session, *, lease: GamingConnectionLease, reason: str = "customer_revoke"
) -> GamingConnectionLease:
    if lease.state == "revoked":
        return lease
    if lease.state in {"pending", "pairing", "failed", "expired"}:
        lease.state = "revoked"
        lease.revoked_at = _now()
        lease.revoked_reason = reason[:80]
        lease.connection_token_hash = ""
        lease.connection_token_expires_at = None
        db.commit(); db.refresh(lease)
        return lease
    if lease.state not in {"paired", "connected", "reconnect_grace"}:
        raise ComputeError("Gaming connection cannot be revoked in its current state.")
    if not lease.sunshine_client_uuid:
        raise ComputeError("Paired connection is missing its Sunshine client identity.")
    pending = db.scalar(
        select(NodeJob).where(
            NodeJob.gaming_session_id == lease.gaming_session_id,
            NodeJob.job_type == "gaming.connection.revoke",
            NodeJob.status.in_(ACTIVE_CONNECTION_JOB_STATES),
            NodeJob.payload["lease_id"].astext == str(lease.id),
        ).limit(1)
    )
    if pending is not None:
        return lease
    lease.state = "revoking"
    lease.revoked_reason = reason[:80]
    lease.connection_token_hash = ""
    lease.connection_token_expires_at = None
    lease.reconnect_grace_expires_at = None
    db.add(NodeJob(
        node_id=lease.node_id,
        gaming_session_id=lease.gaming_session_id,
        job_type="gaming.connection.revoke",
        payload={
            "session_id": str(lease.gaming_session_id),
            "lease_id": str(lease.id),
            "sunshine_client_uuid": lease.sunshine_client_uuid,
        },
    ))
    db.commit(); db.refresh(lease)
    return lease


def record_connection_event(
    db: Session, *, lease: GamingConnectionLease, token: str, event: str,
    reconnect_grace_seconds: int = DEFAULT_RECONNECT_GRACE_SECONDS,
) -> GamingConnectionLease:
    now = _now()
    _verify_connection_token(lease, token, now=now)
    if lease.state in {"revoked", "revoking", "expired", "failed"}:
        raise ComputeError("Gaming connection lease is not active.")
    if lease.state in {"pending", "pairing"}:
        raise ComputeError("Gaming connection has not finished pairing.")

    if event == "connected":
        if lease.state == "reconnect_grace":
            if lease.reconnect_grace_expires_at is None or lease.reconnect_grace_expires_at <= now:
                raise ComputeError("Gaming reconnect grace period has expired.")
        elif lease.state not in {"paired", "connected"}:
            raise ComputeError("Gaming connection cannot enter connected state.")
        if lease.connected_at is None:
            lease.connected_at = now
        lease.state = "connected"
        lease.last_seen_at = now
        lease.disconnected_at = None
        lease.reconnect_grace_expires_at = None

    elif event == "heartbeat":
        if lease.state != "connected":
            raise ComputeError("Connection heartbeat requires an active connection.")
        lease.last_seen_at = now

    elif event == "disconnected":
        if lease.state not in {"connected", "paired", "reconnect_grace"}:
            raise ComputeError("Gaming connection cannot disconnect in its current state.")
        seconds = max(30, min(int(lease.reconnect_grace_seconds or reconnect_grace_seconds), 600))
        lease.state = "reconnect_grace"
        lease.disconnected_at = now
        lease.last_seen_at = now
        lease.reconnect_grace_expires_at = now + timedelta(seconds=seconds)

    elif event == "quit":
        # Explicit quit bypasses reconnect grace and enters the existing secure
        # revoke -> stop -> billing-finalization lifecycle.
        session = db.get(GamingSession, lease.gaming_session_id)
        if session is None:
            raise ComputeError("Gaming session not found.")
        lease.revoked_reason = "customer_quit"
        from app.services.gaming_service import queue_gaming_action
        if session.desired_state == "running":
            queue_gaming_action(db, session=session, action="stop", commit=False)
            db.commit()
        return lease
    else:
        raise ComputeError("Unsupported gaming connection event.")

    db.commit(); db.refresh(lease)
    return lease


def reconcile_connection_leases_for_node(db: Session, *, node_id: UUID) -> list[UUID]:
    """Persisted restart-safe expiry/reconnect reconciliation.

    Pairing/token/reconnect deadlines live in PostgreSQL, so backend restart
    does not reset them. Grace expiry requests the existing secure stop path.
    """
    now = _now()
    stop_ids: list[UUID] = []
    leases = list(db.scalars(select(GamingConnectionLease).where(
        GamingConnectionLease.node_id == node_id,
        GamingConnectionLease.state.in_(ACTIVE_LEASE_STATES),
    )))
    for lease in leases:
        session = db.get(GamingSession, lease.gaming_session_id)
        if session is None:
            continue
        if lease.state in {"pending", "pairing"} and lease.pairing_expires_at <= now:
            lease.state = "expired"
            lease.revoked_reason = "pairing_expired"
            lease.connection_token_hash = ""
            lease.connection_token_expires_at = None
            continue
        token_expired = (
            lease.connection_token_expires_at is not None
            and lease.connection_token_expires_at <= now
        )
        grace_expired = (
            lease.state == "reconnect_grace"
            and lease.reconnect_grace_expires_at is not None
            and lease.reconnect_grace_expires_at <= now
        )
        if not (token_expired or grace_expired):
            continue
        reason = "connection_token_expired" if token_expired else "reconnect_grace_expired"
        lease.revoked_reason = reason
        if session.desired_state == "running":
            from app.services.gaming_service import queue_gaming_action
            queue_gaming_action(db, session=session, action="stop", commit=False)
            stop_ids.append(session.id)
    return stop_ids


def prepare_connection_shutdown(db: Session, *, session: GamingSession) -> bool:
    leases = list(db.scalars(select(GamingConnectionLease).where(
        GamingConnectionLease.gaming_session_id == session.id,
        GamingConnectionLease.state.in_(ACTIVE_LEASE_STATES | {"failed", "expired"}),
    ).order_by(GamingConnectionLease.created_at)))
    waiting = False
    now = _now()
    for lease in leases:
        if lease.state in {"paired", "connected", "reconnect_grace"}:
            if not lease.sunshine_client_uuid:
                lease.state = "failed"
                lease.failure_message = "Paired connection is missing its Sunshine client identity during session shutdown."
                continue
            pending = db.scalar(select(NodeJob).where(
                NodeJob.gaming_session_id == session.id,
                NodeJob.job_type == "gaming.connection.revoke",
                NodeJob.status.in_(ACTIVE_CONNECTION_JOB_STATES),
                NodeJob.payload["lease_id"].astext == str(lease.id),
            ).limit(1))
            if pending is None:
                lease.state = "revoking"
                lease.connection_token_hash = ""
                lease.connection_token_expires_at = None
                lease.reconnect_grace_expires_at = None
                db.add(NodeJob(
                    node_id=lease.node_id, gaming_session_id=session.id,
                    job_type="gaming.connection.revoke",
                    payload={
                        "session_id": str(session.id), "lease_id": str(lease.id),
                        "sunshine_client_uuid": lease.sunshine_client_uuid,
                        "automatic_shutdown": True,
                    },
                ))
            waiting = True
        elif lease.state == "revoking":
            waiting = True
        elif lease.state in NON_PAIRED_INVALIDATABLE_STATES:
            lease.state = "revoked"
            lease.revoked_at = now
            lease.revoked_reason = lease.revoked_reason or "session_shutdown"
            lease.connection_token_hash = ""
            lease.connection_token_expires_at = None
            lease.failure_message = ""
    return not waiting


def continue_deferred_session_action(db: Session, *, session: GamingSession) -> None:
    if session.desired_state not in {"stopped", "terminated"}:
        return
    blocking = db.scalar(select(GamingConnectionLease).where(
        GamingConnectionLease.gaming_session_id == session.id,
        GamingConnectionLease.state.in_({"paired", "connected", "reconnect_grace", "revoking"}),
    ).limit(1))
    if blocking is not None:
        return
    pending_session_job = db.scalar(select(NodeJob).where(
        NodeJob.gaming_session_id == session.id,
        NodeJob.job_type.in_({"gaming.session.stop", "gaming.session.delete"}),
        NodeJob.status.in_(ACTIVE_CONNECTION_JOB_STATES),
    ).limit(1))
    if pending_session_job is not None:
        return
    if session.node_id is None:
        session.status = "error"
        session.failure_category = "missing_node"
        session.failure_message = "Gaming session lost its assigned node during shutdown."
        return
    action = "delete" if session.desired_state == "terminated" else "stop"
    session.status = "terminating" if action == "delete" else "stopping"
    job_type = f"gaming.vm.{action}" if session.deployment_mode == "proxmox_windows_vm" else f"gaming.session.{action}"
    db.add(NodeJob(
        node_id=session.node_id, gaming_session_id=session.id, job_type=job_type,
        payload={"session_id": str(session.id), "gpu_uuid": session.gpu_uuid},
    ))


def finish_connection_job(
    db: Session, *, job: NodeJob, status: str, result: dict, error_message: str
) -> None:
    raw_lease_id = str((job.payload or {}).get("lease_id") or "")
    # Never retain a customer pairing PIN after completion.
    job.payload = {"lease_id": raw_lease_id, "redacted": True}
    try:
        lease_id = UUID(raw_lease_id)
    except (ValueError, TypeError):
        return
    lease = db.get(GamingConnectionLease, lease_id)
    if lease is None:
        return
    if job.job_type == "gaming.connection.pair":
        # A late pairing result must never resurrect a revoked/expired lease.
        if lease.state != "pairing":
            return
        if status != "succeeded":
            lease.state = "failed"
            lease.failure_message = error_message[:500]
            return
        client_uuid = str(result.get("sunshine_client_uuid") or "").strip()
        if not client_uuid:
            lease.state = "failed"
            lease.failure_message = "Node paired the connection without returning a Sunshine client UUID."
            return
        lease.state = "paired"
        lease.sunshine_client_uuid = client_uuid
        lease.paired_at = _now()
        lease.failure_message = ""
        return
    if job.job_type == "gaming.connection.revoke":
        if lease.state != "revoking":
            return
        session = db.get(GamingSession, lease.gaming_session_id)
        if status != "succeeded":
            lease.state = "failed"
            lease.failure_message = error_message[:500]
            if session is not None and session.desired_state in {"stopped", "terminated"}:
                session.status = "error"
                session.failure_category = "connection_revocation_failed"
                session.failure_message = "Secure gaming connection revocation failed; runtime shutdown was not attempted."
            return
        lease.state = "revoked"
        lease.revoked_at = _now()
        lease.connection_token_hash = ""
        lease.connection_token_expires_at = None
        lease.reconnect_grace_expires_at = None
        lease.failure_message = ""
        if session is not None:
            continue_deferred_session_action(db, session=session)
