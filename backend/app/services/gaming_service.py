from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compute import GamingReservation, GamingSession, NodeCapacity, NodeJob
from app.models.gaming_catalog import GamingTitle, NodeGameQualification
from app.services.gaming_catalog_service import qualification_is_fresh
from app.models.node import Node
from app.models.user import User
from app.schemas.compute import GamingSessionCreate
from app.services.compute_service import ComputeError, has_capacity, _resolve_organization
from app.services.organization_service import visible_organizations

GIB = 1024 ** 3
ACTIVE_RESERVATION_STATES = {"reserved", "active"}
TERMINAL_SESSION_STATES = {"terminated", "failed"}


def _gpu_inventory(node: Node) -> list[dict]:
    inventory = node.inventory or {}
    gpu = inventory.get("gpu") or inventory.get("nvidia") or {}
    devices = gpu.get("gpus", []) if isinstance(gpu, dict) else []
    if not devices:
        devices = inventory.get("gpus", [])
    return [item for item in devices if isinstance(item, dict)]


def _gpu_fields(item: dict) -> tuple[str, str, int]:
    gpu_uuid = str(item.get("uuid") or item.get("gpu_uuid") or "")
    name = str(item.get("name") or item.get("model") or "")
    raw_vram = item.get("memory_total_mib", item.get("vram_mb", item.get("memory_mb", 0)))
    try:
        vram = int(raw_vram or 0)
    except (TypeError, ValueError):
        vram = 0
    return gpu_uuid, name, vram


def _reserved_gpu_uuids(db: Session, node_id: UUID) -> set[str]:
    return set(db.scalars(select(GamingReservation.gpu_uuid).where(
        GamingReservation.node_id == node_id,
        GamingReservation.status.in_(ACTIVE_RESERVATION_STATES),
    )))


# KG-001 catalog-aware scheduling
def _resolve_gaming_title(db: Session, game_slug: str | None) -> GamingTitle | None:
    if not game_slug:
        return None
    title = db.scalar(select(GamingTitle).where(GamingTitle.slug == game_slug, GamingTitle.enabled.is_(True)))
    if title is None:
        raise ComputeError(f"Unknown or disabled gaming title: {game_slug}")
    return title


def _qualified_node_ids(db: Session, title: GamingTitle) -> set[UUID]:
    rows = db.scalars(
        select(NodeGameQualification).where(
            NodeGameQualification.gaming_title_id == title.id,
            NodeGameQualification.qualified.is_(True),
            NodeGameQualification.policy_version
            == title.qualification_policy_version,
        )
    )
    return {
        row.node_id
        for row in rows
        if qualification_is_fresh(row)
    }


def select_gaming_host(db: Session, *, minimum_vram_mb: int, cpu: int, memory_bytes: int, storage_bytes: int, gaming_title: GamingTitle | None = None):
    rows = db.execute(
        select(NodeCapacity, Node)
        .join(Node, Node.id == NodeCapacity.node_id)
        .where(Node.lifecycle_state == "approved")
        .where(Node.connectivity_state == "online")
        .where(Node.is_enabled.is_(True))
        .where(Node.intended_purpose == "gaming_host")
        .with_for_update(of=NodeCapacity)
    ).all()
    candidates = []
    qualified_nodes = _qualified_node_ids(db, gaming_title) if gaming_title is not None else None
    for capacity, node in rows:
        if qualified_nodes is not None and node.id not in qualified_nodes:
            continue
        if not has_capacity(capacity, cpu=cpu, memory_bytes=memory_bytes, storage_bytes=storage_bytes):
            continue
        reserved = _reserved_gpu_uuids(db, node.id)
        for gpu in _gpu_inventory(node):
            gpu_uuid, name, vram = _gpu_fields(gpu)
            if not gpu_uuid or gpu_uuid in reserved or vram < minimum_vram_mb:
                continue
            candidates.append((vram, capacity.memory_allocatable_bytes - capacity.memory_allocated_bytes, capacity, node, gpu_uuid, name))
    if not candidates:
        raise ComputeError(f"No gaming host has a free operational GPU with at least {minimum_vram_mb} MiB VRAM and the requested host capacity.")
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, capacity, node, gpu_uuid, name = candidates[0]
    vram = next(_gpu_fields(g)[2] for g in _gpu_inventory(node) if _gpu_fields(g)[0] == gpu_uuid)
    return capacity, node, gpu_uuid, name, vram


def create_gaming_session(db: Session, *, payload: GamingSessionCreate, actor: User) -> GamingSession:
    organization_id = _resolve_organization(db, actor, payload.organization_id)
    memory_bytes = payload.memory_mb * 1024 ** 2
    storage_bytes = payload.storage_gb * GIB
    gaming_title = _resolve_gaming_title(db, payload.game_slug)
    effective_vram = max(payload.minimum_vram_mb, gaming_title.minimum_vram_mb if gaming_title else 0)
    capacity, node, gpu_uuid, gpu_name, gpu_vram = select_gaming_host(
        db, minimum_vram_mb=effective_vram, cpu=payload.cpu,
        memory_bytes=memory_bytes, storage_bytes=storage_bytes,
        gaming_title=gaming_title,
    )
    session = GamingSession(
        gaming_title_id=(gaming_title.id if gaming_title else None),
        organization_id=organization_id, created_by_user_id=actor.id, node_id=node.id,
        name=payload.name, status="provisioning", desired_state="running",
        minimum_vram_mb=effective_vram, requested_cpu=payload.cpu,
        requested_memory_bytes=memory_bytes, requested_storage_bytes=storage_bytes,
        gpu_uuid=gpu_uuid, gpu_name=gpu_name, gpu_vram_mb=gpu_vram,
        streaming_backend=payload.streaming_backend,
    )
    db.add(session); db.flush()
    reservation = GamingReservation(
        gaming_session_id=session.id, node_id=node.id, gpu_uuid=gpu_uuid,
        cpu=payload.cpu, memory_bytes=memory_bytes, storage_bytes=storage_bytes,
        status="reserved",
    )
    db.add(reservation)
    capacity.cpu_allocated += payload.cpu
    capacity.memory_allocated_bytes += memory_bytes
    capacity.storage_allocated_bytes += storage_bytes
    db.add(NodeJob(
        node_id=node.id, gaming_session_id=session.id, job_type="gaming.session.create",
        payload={"session_id": str(session.id), "gpu_uuid": gpu_uuid, "gpu_name": gpu_name,
                 "minimum_vram_mb": effective_vram, "streaming_backend": payload.streaming_backend, "game_slug": (gaming_title.slug if gaming_title else None), "launcher": (gaming_title.launcher if gaming_title else None), "launcher_app_id": (gaming_title.launcher_app_id if gaming_title else None)},
    ))
    db.commit(); db.refresh(session)
    return session


def visible_gaming_sessions(db: Session, actor: User) -> list[GamingSession]:
    org_ids = [o.id for o in visible_organizations(db, actor)]
    if not org_ids:
        return []
    return list(db.scalars(select(GamingSession).where(GamingSession.organization_id.in_(org_ids)).order_by(GamingSession.created_at.desc())))


def get_visible_gaming_session(db: Session, actor: User, session_id: UUID) -> GamingSession:
    item = db.get(GamingSession, session_id)
    if item is None or item.organization_id not in {o.id for o in visible_organizations(db, actor)}:
        raise ComputeError("Gaming session not found.")
    return item


def release_gaming_reservation(db: Session, session: GamingSession) -> None:
    reservation = db.scalar(select(GamingReservation).where(GamingReservation.gaming_session_id == session.id).with_for_update())
    if reservation is None or reservation.status not in ACTIVE_RESERVATION_STATES:
        return
    capacity = db.scalar(select(NodeCapacity).where(NodeCapacity.node_id == reservation.node_id).with_for_update())
    if capacity is not None:
        capacity.cpu_allocated = max(0, capacity.cpu_allocated - reservation.cpu)
        capacity.memory_allocated_bytes = max(0, capacity.memory_allocated_bytes - reservation.memory_bytes)
        capacity.storage_allocated_bytes = max(0, capacity.storage_allocated_bytes - reservation.storage_bytes)
    reservation.status = "released"; reservation.released_at = datetime.now(UTC)


def queue_gaming_action(db: Session, *, session: GamingSession, action: str) -> GamingSession:
    if action not in {"start", "stop", "terminate"}:
        raise ComputeError("Unsupported gaming session action.")
    if session.status in TERMINAL_SESSION_STATES:
        if action == "terminate" and session.status == "terminated":
            return session
        raise ComputeError("Gaming session is already terminal.")
    pending = db.scalar(select(NodeJob).where(
        NodeJob.gaming_session_id == session.id, NodeJob.status.in_({"pending", "running"})
    ).limit(1))
    if pending is not None:
        raise ComputeError("Gaming session already has an in-flight operation.")
    job_action = "delete" if action == "terminate" else action
    session.desired_state = "terminated" if action == "terminate" else ("running" if action == "start" else "stopped")
    session.status = "terminating" if action == "terminate" else f"{action}ing"
    db.add(NodeJob(node_id=session.node_id, gaming_session_id=session.id, job_type=f"gaming.session.{job_action}", payload={"session_id": str(session.id), "gpu_uuid": session.gpu_uuid}))
    db.commit(); db.refresh(session)
    return session


def finish_gaming_job(
    db: Session,
    *,
    job: NodeJob,
    status: str,
    result: dict,
    error_message: str,
) -> None:
    """Reconcile an authoritative node-job result into gaming state.

    Creation failures are terminal because no usable runtime was established.
    Start/stop/delete failures are recoverable errors: the reservation is kept
    until Khan Cloud can retry or reconcile the real host state. This avoids
    releasing a GPU that may still have a live runtime on the provider machine.
    """

    if job.gaming_session_id is None:
        return

    session = db.get(GamingSession, job.gaming_session_id)
    if session is None:
        return

    reservation = db.scalar(
        select(GamingReservation).where(
            GamingReservation.gaming_session_id == session.id
        )
    )

    if status == "succeeded":
        session.failure_category = ""
        session.failure_message = ""

        if job.job_type == "gaming.session.create":
            runtime_id = str(result.get("runtime_id") or "").strip()
            if not runtime_id:
                session.status = "failed"
                session.failure_category = "invalid_node_result"
                session.failure_message = (
                    "Gaming runtime creation succeeded without a runtime_id."
                )
                release_gaming_reservation(db, session)
                return

            session.status = "running"
            session.runtime_id = runtime_id
            session.connection_info = dict(
                result.get("connection_info") or {}
            )
            session.started_at = datetime.now(UTC)
            if reservation is not None:
                reservation.status = "active"

        elif job.job_type == "gaming.session.start":
            session.status = "running"
            session.started_at = session.started_at or datetime.now(UTC)
            session.connection_info = dict(
                result.get("connection_info") or {}
            )

        elif job.job_type == "gaming.session.stop":
            session.status = "stopped"
            session.connection_info = {}

        elif job.job_type == "gaming.session.delete":
            session.status = "terminated"
            session.ended_at = datetime.now(UTC)
            session.connection_info = {}
            release_gaming_reservation(db, session)

        return

    session.failure_category = "node_job_failed"
    session.failure_message = error_message[:500]

    if job.job_type == "gaming.session.create":
        session.status = "failed"
        release_gaming_reservation(db, session)
    else:
        # The real machine may still own the runtime/GPU after a failed
        # start/stop/delete operation. Keep the reservation and allow retry.
        session.status = "error"
