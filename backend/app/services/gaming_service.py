from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compute import GamingReservation, GamingSession, GamingVmBlueprint, NodeCapacity, NodeJob
from app.models.gaming_catalog import GamingTitle, NodeGameQualification
from app.services.gaming_catalog_service import qualification_is_fresh
from app.models.node import Node
from app.models.deployment_profile import DeploymentProfile
from app.models.user import User
from app.schemas.compute import GamingSessionCreate
from app.services.gaming_display_policy import (
    GamingDisplayPolicyError,
    attach_display_policy,
    constraints_for_session_request,
)
from app.services.compute_service import ComputeError, has_capacity, _resolve_organization
from app.services.organization_service import visible_organizations

GIB = 1024 ** 3
ACTIVE_RESERVATION_STATES = {"reserved", "active"}
TERMINAL_SESSION_STATES = {"terminated", "failed"}
GAMING_HEARTBEAT_STALE_AFTER_SECONDS = 300
GAMING_RUNTIME_HEALTH_FAILURE_THRESHOLD = 3
GAMING_QUARANTINE_AUTO_RECOVERY_MAX_ATTEMPTS = 3
GAMING_QUARANTINE_AUTO_RECOVERY_COOLDOWN_SECONDS = 60
GAMING_RUNTIME_CRITICAL_REASONS = {
    "interactive_session_unavailable",
    "sunshine_unavailable",
    "gpu_unavailable",
}

# KG-009 placement policy.
#
# Qualification/readiness/capacity are hard admission gates.
# Ownership preference is applied only after a node has passed all
# mandatory gaming requirements.
GAMING_OWNERSHIP_PRIORITY = {
    "khan_cloud": 0,
    "trusted_partner": 1,
    "organization": 2,
    "third_party_provider": 3,
}
GAMING_UNKNOWN_OWNERSHIP_PRIORITY = 99


def _node_ownership_type(
    db: Session,
    node: Node,
) -> str:
    if node.deployment_profile_id is None:
        return "unknown"

    profile = db.get(
        DeploymentProfile,
        node.deployment_profile_id,
    )

    if profile is None:
        return "unknown"

    return str(
        profile.ownership_type or "unknown"
    ).strip().lower()


def _gaming_placement_rank(
    *,
    ownership_type: str,
    gpu_vram_mb: int,
    available_memory_bytes: int,
) -> tuple[int, int, int]:
    """
    Produce the deterministic gaming placement rank.

    Lower tuple wins.

    1. Khan Cloud capacity first.
    2. Then trusted/marketplace fallback capacity.
    3. Within the same ownership tier retain the existing preference
       for the strongest free GPU and greatest available memory.

    This function MUST NOT be used as an admission check. Nodes reach
    this ranking only after readiness, title qualification and host
    capacity have already passed.
    """
    priority = GAMING_OWNERSHIP_PRIORITY.get(
        ownership_type,
        GAMING_UNKNOWN_OWNERSHIP_PRIORITY,
    )

    return (
        priority,
        -int(gpu_vram_mb),
        -int(available_memory_bytes),
    )


def _gaming_placement_metadata(
    db: Session,
    node: Node,
) -> dict[str, object]:
    ownership_type = _node_ownership_type(
        db,
        node,
    )

    return {
        "policy_version": "kg009-v1",
        "ownership_type": ownership_type,
        "khan_owned": ownership_type == "khan_cloud",
        "fallback_capacity": ownership_type != "khan_cloud",
    }


def _gaming_inventory(node: Node) -> dict:
    inventory = node.inventory or {}
    gaming = inventory.get("gaming", {})
    return gaming if isinstance(gaming, dict) else {}


def _interactive_session_ready(node: Node) -> bool:
    gaming = _gaming_inventory(node)
    session = gaming.get("interactive_session", {})
    return bool(
        isinstance(session, dict)
        and session.get("available", False)
        and session.get("session_id") is not None
    )


def _sunshine_ready(node: Node) -> bool:
    gaming = _gaming_inventory(node)
    streaming = gaming.get("streaming", {})
    if not isinstance(streaming, dict):
        return False
    sunshine = streaming.get("sunshine", {})
    return bool(
        isinstance(sunshine, dict)
        and sunshine.get("installed", False)
        and sunshine.get("ready", False)
    )


def gaming_host_readiness_reasons(
    node: Node,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = GAMING_HEARTBEAT_STALE_AFTER_SECONDS,
) -> list[str]:
    from app.services.deployment_operations_service import effective_connectivity

    reasons: list[str] = []
    current = now or datetime.now(UTC)

    if node.lifecycle_state != "approved":
        reasons.append("node_not_approved")

    if not node.is_enabled:
        reasons.append("node_disabled")

    if node.intended_purpose != "gaming_host":
        reasons.append("node_not_gaming_host")

    if not node.gaming_accepting_work:
        reasons.append("gaming_work_disabled")

    connectivity = effective_connectivity(
        node,
        now=current,
        stale_after_seconds=stale_after_seconds,
    )
    if connectivity != "online":
        reasons.append(f"node_{connectivity}")

    if not _interactive_session_ready(node):
        reasons.append("interactive_session_unavailable")

    if not _sunshine_ready(node):
        reasons.append("sunshine_unavailable")

    if not node.nvidia_available or node.gpu_count <= 0:
        reasons.append("gpu_unavailable")

    return reasons


def gaming_runtime_critical_reasons(
    node: Node,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = GAMING_HEARTBEAT_STALE_AFTER_SECONDS,
) -> list[str]:
    """Runtime-critical signals independent of the admission switch."""
    reasons = set(gaming_host_readiness_reasons(
        node, now=now
    ))
    return sorted(reasons.intersection(GAMING_RUNTIME_CRITICAL_REASONS))


def reconcile_gaming_node_admission_health(
    db: Session,
    *,
    node: Node,
) -> dict[str, object]:
    """Block new work on first critical failure; preserve C3 session hysteresis."""
    now = datetime.now(UTC)
    critical = gaming_runtime_critical_reasons(node, now=now)

    if critical:
        if node.gaming_health_state != "degraded":
            node.gaming_health_degraded_at = now
        node.gaming_health_state = "degraded"
        node.gaming_health_reasons = {"critical": critical}
        node.gaming_health_recovered_at = None
        if node.lifecycle_state == "approved" and node.gaming_accepting_work:
            node.gaming_accepting_work = False
            node.gaming_admission_auto_blocked = True
    else:
        was_degraded = node.gaming_health_state == "degraded"
        node.gaming_health_state = "healthy"
        node.gaming_health_reasons = {}
        if was_degraded:
            node.gaming_health_recovered_at = now
        if (
            node.gaming_admission_auto_blocked
            and node.lifecycle_state == "approved"
            and node.is_enabled
        ):
            node.gaming_accepting_work = True
            node.gaming_admission_auto_blocked = False

    db.flush()
    return {
        "state": node.gaming_health_state,
        "critical_reasons": critical,
        "admission_auto_blocked": node.gaming_admission_auto_blocked,
        "accepting_work": node.gaming_accepting_work,
    }


def gaming_host_is_ready(
    node: Node,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = GAMING_HEARTBEAT_STALE_AFTER_SECONDS,
) -> bool:
    return not gaming_host_readiness_reasons(
        node,
        now=now,
        stale_after_seconds=stale_after_seconds,
    )


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
        .where(Node.is_enabled.is_(True))
        .where(Node.gaming_accepting_work.is_(True))
        .where(Node.intended_purpose == "gaming_host")
        .with_for_update(of=NodeCapacity)
    ).all()
    candidates = []
    qualified_nodes = _qualified_node_ids(db, gaming_title) if gaming_title is not None else None
    for capacity, node in rows:
        if not gaming_host_is_ready(node):
            continue
        if qualified_nodes is not None and node.id not in qualified_nodes:
            continue
        if not has_capacity(capacity, cpu=cpu, memory_bytes=memory_bytes, storage_bytes=storage_bytes):
            continue
        reserved = _reserved_gpu_uuids(db, node.id)
        for gpu in _gpu_inventory(node):
            gpu_uuid, name, vram = _gpu_fields(gpu)
            if not gpu_uuid or gpu_uuid in reserved or vram < minimum_vram_mb:
                continue
            available_memory = (
                capacity.memory_allocatable_bytes
                - capacity.memory_allocated_bytes
            )
            ownership_type = _node_ownership_type(
                db,
                node,
            )
            rank = _gaming_placement_rank(
                ownership_type=ownership_type,
                gpu_vram_mb=vram,
                available_memory_bytes=available_memory,
            )
            candidates.append(
                (
                    rank,
                    capacity,
                    node,
                    gpu_uuid,
                    name,
                    vram,
                )
            )

    if not candidates:
        raise ComputeError(
            "No gaming host has a free operational GPU with at least "
            f"{minimum_vram_mb} MiB VRAM and the requested host capacity."
        )

    candidates.sort(
        key=lambda item: item[0]
    )

    (
        _rank,
        capacity,
        node,
        gpu_uuid,
        name,
        vram,
    ) = candidates[0]

    return capacity, node, gpu_uuid, name, vram



def _gaming_session_display_policy(
    payload: GamingSessionCreate,
) -> dict[str, object]:
    """
    Build the VDD policy for one gaming session.

    The control plane owns product/client constraints. The Node Agent
    independently validates the resulting runtime policy before applying it.
    """

    constraints = constraints_for_session_request(
        display_profile=payload.display_profile,
        max_width=payload.display_max_width,
        max_height=payload.display_max_height,
        max_refresh_hz=payload.display_max_refresh_hz,
        preferred_width=payload.display_preferred_width,
        preferred_height=payload.display_preferred_height,
        preferred_refresh_hz=payload.display_preferred_refresh_hz,
        hdr_requested=payload.hdr_requested,
        hdr_capable=payload.client_hdr_capable,
        allow_4k=payload.display_allow_4k,
        allow_240hz=payload.display_allow_240hz,
    )

    wrapped = attach_display_policy(
        {},
        constraints,
    )

    policy = wrapped["display_policy"]

    if not isinstance(policy, dict):
        raise GamingDisplayPolicyError(
            "Derived gaming display policy is invalid."
        )

    return policy

def create_gaming_session(db: Session, *, payload: GamingSessionCreate, actor: User) -> GamingSession:
    organization_id = _resolve_organization(db, actor, payload.organization_id)
    memory_bytes = payload.memory_mb * 1024 ** 2
    storage_bytes = payload.storage_gb * GIB
    gaming_title = _resolve_gaming_title(db, payload.game_slug)
    effective_vram = max(payload.minimum_vram_mb, gaming_title.minimum_vram_mb if gaming_title else 0)

    if payload.play_request_id is not None:
        existing = db.scalar(
            select(GamingSession).where(
                GamingSession.play_request_id == payload.play_request_id
            )
        )
        if existing is not None:
            if (
                existing.organization_id != organization_id
                or existing.created_by_user_id != actor.id
            ):
                raise ComputeError(
                    "Play request ID is already bound to another gaming request."
                )
            return existing

    commercial_admission = None
    if gaming_title is not None:
        from app.services.gaming_billing_service import (
            GamingBillingError,
            resolve_gaming_commercial_admission,
        )
        try:
            commercial_admission = resolve_gaming_commercial_admission(
                db,
                title=gaming_title,
                organization_id=organization_id,
            )
        except GamingBillingError as exc:
            raise ComputeError(str(exc)) from exc

    if payload.deployment_mode == "proxmox_windows_vm":
        from app.services.gaming_vm_service import resolve_blueprint, select_gaming_hypervisor, queue_windows_vm_create
        blueprint = resolve_blueprint(db, payload.blueprint_slug)
        capacity, node, gpu = select_gaming_hypervisor(db, cpu=payload.cpu, memory_bytes=memory_bytes, storage_bytes=storage_bytes, minimum_vram_mb=effective_vram)
        gpu_uuid = str(gpu.get("uuid") or gpu.get("slot") or "")
        gpu_name = str(gpu.get("name") or "passthrough-gpu")
        gpu_vram = int(gpu.get("memory_total_mib") or 0)
        session = GamingSession(gaming_title_id=(gaming_title.id if gaming_title else None), play_request_id=payload.play_request_id, organization_id=organization_id, created_by_user_id=actor.id, node_id=node.id, deployment_mode="proxmox_windows_vm", deployment_blueprint_id=blueprint.id, deployment_stage="reserving", name=payload.name, status="provisioning", desired_state="running", minimum_vram_mb=effective_vram, requested_cpu=payload.cpu, requested_memory_bytes=memory_bytes, requested_storage_bytes=storage_bytes, gpu_uuid=gpu_uuid, gpu_name=gpu_name, gpu_vram_mb=gpu_vram, streaming_backend=payload.streaming_backend)
        db.add(session); db.flush()
        if commercial_admission is not None:
            from app.services.gaming_billing_service import (
                GamingBillingError,
                bind_gaming_host_economics,
                reserve_gaming_admission,
            )
            try:
                reserve_gaming_admission(
                    db, session=session, admission=commercial_admission
                )
                bind_gaming_host_economics(
                    db,
                    session=session,
                    node=node,
                    ownership_type=_node_ownership_type(db, node),
                )
            except GamingBillingError as exc:
                db.rollback()
                raise ComputeError(str(exc)) from exc
        db.add(GamingReservation(gaming_session_id=session.id,node_id=node.id,gpu_uuid=gpu_uuid,cpu=payload.cpu,memory_bytes=memory_bytes,storage_bytes=storage_bytes,status="reserved"))
        capacity.cpu_allocated += payload.cpu; capacity.memory_allocated_bytes += memory_bytes; capacity.storage_allocated_bytes += storage_bytes
        queue_windows_vm_create(db, session=session, capacity=capacity, hypervisor=node, blueprint=blueprint, gpu=gpu)
        db.commit(); db.refresh(session); return session

    capacity, node, gpu_uuid, gpu_name, gpu_vram = select_gaming_host(db, minimum_vram_mb=effective_vram, cpu=payload.cpu, memory_bytes=memory_bytes, storage_bytes=storage_bytes, gaming_title=gaming_title)
    session = GamingSession(gaming_title_id=(gaming_title.id if gaming_title else None), play_request_id=payload.play_request_id, organization_id=organization_id, created_by_user_id=actor.id, node_id=node.id, deployment_mode="bare_metal", deployment_stage="runtime_queued", name=payload.name, status="provisioning", desired_state="running", minimum_vram_mb=effective_vram, requested_cpu=payload.cpu, requested_memory_bytes=memory_bytes, requested_storage_bytes=storage_bytes, gpu_uuid=gpu_uuid, gpu_name=gpu_name, gpu_vram_mb=gpu_vram, streaming_backend=payload.streaming_backend)
    db.add(session); db.flush()
    if commercial_admission is not None:
        from app.services.gaming_billing_service import (
            GamingBillingError,
            bind_gaming_host_economics,
            reserve_gaming_admission,
        )
        try:
            reserve_gaming_admission(
                db, session=session, admission=commercial_admission
            )
            bind_gaming_host_economics(
                db,
                session=session,
                node=node,
                ownership_type=_node_ownership_type(db, node),
            )
        except GamingBillingError as exc:
            db.rollback()
            raise ComputeError(str(exc)) from exc
    db.add(GamingReservation(gaming_session_id=session.id,node_id=node.id,gpu_uuid=gpu_uuid,cpu=payload.cpu,memory_bytes=memory_bytes,storage_bytes=storage_bytes,status="reserved"))
    capacity.cpu_allocated += payload.cpu; capacity.memory_allocated_bytes += memory_bytes; capacity.storage_allocated_bytes += storage_bytes
    display_policy = _gaming_session_display_policy(payload)

    # A gaming session owns one immutable initial VDD policy stream.
    # Later runtime-policy updates may advance this stream's revision.
    display_policy["policy_id"] = (
        f"gaming-session:{session.id}"
    )
    display_policy["revision"] = 1

    db.add(
        NodeJob(
            node_id=node.id,
            gaming_session_id=session.id,
            job_type="gaming.session.create",
            payload={
                "session_id": str(session.id),
                "gpu_uuid": gpu_uuid,
                "gpu_name": gpu_name,
                "minimum_vram_mb": effective_vram,
                "streaming_backend": payload.streaming_backend,
                "game_slug": (
                    gaming_title.slug
                    if gaming_title
                    else None
                ),
                "launcher": (
                    gaming_title.launcher
                    if gaming_title
                    else None
                ),
                "launcher_app_id": (
                    gaming_title.launcher_app_id
                    if gaming_title
                    else None
                ),
                "display_policy": display_policy,
                "placement": _gaming_placement_metadata(
                    db,
                    node,
                ),
            },
        )
    )
    db.commit(); db.refresh(session); return session


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


def _gaming_runtime_job_type(session: GamingSession, action: str) -> str:
    if session.deployment_mode == "proxmox_windows_vm":
        mapping = {"start":"gaming.vm.start","stop":"gaming.vm.stop","delete":"gaming.vm.delete"}
        return mapping[action]
    return f"gaming.session.{action}"


def queue_gaming_action(
    db: Session,
    *,
    session: GamingSession,
    action: str,
    commit: bool = True,
) -> GamingSession:
    if action not in {"start", "stop", "terminate"}:
        raise ComputeError("Unsupported gaming session action.")

    if session.status in TERMINAL_SESSION_STATES:
        if action == "terminate" and session.status == "terminated":
            return session
        raise ComputeError("Gaming session is already terminal.")

    pending = db.scalar(
        select(NodeJob)
        .where(
            NodeJob.gaming_session_id == session.id,
            NodeJob.status.in_({"pending", "running"}),
        )
        .limit(1)
    )

    if pending is not None:
        raise ComputeError(
            "Gaming session already has an in-flight operation."
        )

    if session.node_id is None:
        raise ComputeError(
            "Gaming session is not assigned to a node."
        )

    if action == "start":
        from app.services.gaming_billing_service import (
            GamingBillingError,
            reopen_gaming_billing,
        )
        try:
            reopen_gaming_billing(db, session=session)
        except GamingBillingError as exc:
            raise ComputeError(str(exc)) from exc
        session.desired_state = "running"
        session.status = "starting"

        db.add(
            NodeJob(
                node_id=session.node_id,
                gaming_session_id=session.id,
                job_type=_gaming_runtime_job_type(session, "start"),
                payload={
                    "session_id": str(session.id),
                    "gpu_uuid": session.gpu_uuid,
                },
            )
        )

        if commit:
            db.commit()
            db.refresh(session)
        else:
            db.flush()
        return session

    # Stop and terminate are security-sensitive. Revoke any active
    # Sunshine client authorization before stopping/deleting runtime.
    from app.services.gaming_connection_service import (
        prepare_connection_shutdown,
    )

    session.desired_state = (
        "terminated"
        if action == "terminate"
        else "stopped"
    )
    if action == "terminate":
        # KG-009C5: capacity remains reserved until node cleanup is proven.
        session.sanitization_state = "pending"
        session.quarantine_reason = ""

    ready = prepare_connection_shutdown(
        db,
        session=session,
    )

    if ready:
        job_action = (
            "delete"
            if action == "terminate"
            else "stop"
        )

        session.status = (
            "terminating"
            if action == "terminate"
            else "stopping"
        )

        db.add(
            NodeJob(
                node_id=session.node_id,
                gaming_session_id=session.id,
                job_type=_gaming_runtime_job_type(session, job_action),
                payload={
                    "session_id": str(session.id),
                    "gpu_uuid": session.gpu_uuid,
                },
            )
        )
    else:
        # The desired state persists the deferred action. Successful
        # connection revocation will enqueue the runtime operation.
        session.status = (
            "terminating"
            if action == "terminate"
            else "stopping"
        )

    if commit:
        db.commit()
        db.refresh(session)
    else:
        db.flush()
    return session




def gaming_node_active_reservation_count(db: Session, *, node_id: UUID) -> int:
    """Count capacity still owned by gaming sessions on this node."""
    from sqlalchemy import func
    return int(
        db.scalar(
            select(func.count(GamingReservation.id)).where(
                GamingReservation.node_id == node_id,
                GamingReservation.status.in_(ACTIVE_RESERVATION_STATES),
            )
        )
        or 0
    )


def gaming_node_inflight_job_count(db: Session, *, node_id: UUID) -> int:
    """Count unfinished gaming jobs that must settle before maintenance."""
    from sqlalchemy import func
    return int(
        db.scalar(
            select(func.count(NodeJob.id)).where(
                NodeJob.node_id == node_id,
                NodeJob.gaming_session_id.is_not(None),
                NodeJob.status.in_({"pending", "running"}),
            )
        )
        or 0
    )


def gaming_recovery_readiness_reasons(
    node: Node,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Runtime cleanup readiness independent of scheduler admission.

    Draining/maintenance hosts must remain able to prove cleanup without
    becoming placement-eligible. Disabled/retired/rejected hosts remain
    outside automatic recovery.
    """
    from app.services.deployment_operations_service import effective_connectivity

    reasons: list[str] = []
    current = now or datetime.now(UTC)

    if node.intended_purpose != "gaming_host":
        reasons.append("node_not_gaming_host")
    if node.lifecycle_state not in {"approved", "draining", "maintenance"}:
        reasons.append(f"node_lifecycle_{node.lifecycle_state}")
    if not node.is_enabled:
        reasons.append("node_disabled")

    connectivity = effective_connectivity(
        node,
        now=current,
        stale_after_seconds=GAMING_HEARTBEAT_STALE_AFTER_SECONDS,
    )
    if connectivity != "online":
        reasons.append(f"node_{connectivity}")
    if not _interactive_session_ready(node):
        reasons.append("interactive_session_unavailable")
    if not _sunshine_ready(node):
        reasons.append("sunshine_unavailable")
    if not node.nvidia_available or node.gpu_count <= 0:
        reasons.append("gpu_unavailable")

    return reasons


def gaming_maintenance_reentry_reasons(
    db: Session,
    *,
    node: Node,
    now: datetime | None = None,
) -> list[str]:
    """Safety gates for maintenance -> approved on a gaming host.

    This intentionally evaluates the physical/runtime readiness signals while
    ignoring the maintenance lifecycle and drain admission flag themselves.
    They are restored only after every safety gate passes.
    """
    from app.services.deployment_operations_service import effective_connectivity

    reasons: list[str] = []
    current = now or datetime.now(UTC)

    if node.lifecycle_state != "maintenance":
        reasons.append("node_not_in_maintenance")
    if node.intended_purpose != "gaming_host":
        reasons.append("node_not_gaming_host")
    if gaming_node_active_reservation_count(db, node_id=node.id):
        reasons.append("active_gaming_reservations")
    if gaming_node_inflight_job_count(db, node_id=node.id):
        reasons.append("inflight_gaming_jobs")
    if node.gaming_health_state != "healthy":
        reasons.append("gaming_health_degraded")

    capacity = db.scalar(
        select(NodeCapacity).where(NodeCapacity.node_id == node.id)
    )
    if capacity is None:
        reasons.append("node_capacity_missing")
    else:
        if not capacity.execution_enabled:
            reasons.append("capacity_execution_disabled")
        if not capacity.scheduling_enabled:
            reasons.append("capacity_scheduling_disabled")

    connectivity = effective_connectivity(
        node,
        now=current,
        stale_after_seconds=GAMING_HEARTBEAT_STALE_AFTER_SECONDS,
    )
    if connectivity != "online":
        reasons.append(f"node_{connectivity}")
    if not _interactive_session_ready(node):
        reasons.append("interactive_session_unavailable")
    if not _sunshine_ready(node):
        reasons.append("sunshine_unavailable")
    if not node.nvidia_available or node.gpu_count <= 0:
        reasons.append("gpu_unavailable")

    return reasons


def request_gaming_node_drain(
    db: Session,
    *,
    node: Node,
    actor_user_id: UUID,
    reason: str = "",
    terminate_active_sessions: bool = False,
) -> Node:
    """Enter drain without inventing a second scheduling or teardown system."""
    from app.services.audit_service import record_audit_event
    from app.services.node_service import transition_node

    if node.intended_purpose != "gaming_host":
        raise ComputeError("Gaming drain applies only to gaming_host nodes.")
    if node.lifecycle_state != "approved":
        raise ComputeError("Gaming drain requires an approved node.")

    # Serialize against select_gaming_host(), which locks the same capacity
    # row before returning a placement candidate. Once this lock is acquired,
    # the lifecycle/admission transition commits before a waiting scheduler
    # can continue.
    capacity = db.scalar(
        select(NodeCapacity)
        .where(NodeCapacity.node_id == node.id)
        .with_for_update()
    )
    if capacity is None:
        raise ComputeError("Gaming drain requires an authoritative node capacity row.")

    # transition_node commits the admission barrier while holding the shared
    # scheduler/drain serialization point. New placement is blocked before
    # therefore blocked before any optional evacuation work is queued.
    transition_node(
        db,
        node=node,
        new_state="draining",
        actor_user_id=actor_user_id,
        reason=reason,
    )

    queued: list[str] = []
    blocked: list[str] = []
    if terminate_active_sessions:
        sessions = list(
            db.scalars(
                select(GamingSession).where(
                    GamingSession.node_id == node.id,
                    GamingSession.desired_state != "terminated",
                    GamingSession.status.notin_(TERMINAL_SESSION_STATES),
                )
            )
        )
        for session in sessions:
            try:
                queue_gaming_action(
                    db,
                    session=session,
                    action="terminate",
                    commit=False,
                )
                queued.append(str(session.id))
            except ComputeError:
                # Existing in-flight work remains authoritative. The heartbeat
                # drain reconciler waits rather than bypassing that operation.
                blocked.append(str(session.id))
        db.commit()
        db.refresh(node)

    record_audit_event(
        db,
        actor_user_id=actor_user_id,
        action="node.gaming_drain_requested",
        resource_type="node",
        resource_id=str(node.id),
        reason=reason,
        details={
            "terminate_active_sessions": terminate_active_sessions,
            "termination_queued_session_ids": queued,
            "inflight_blocked_session_ids": blocked,
        },
    )
    db.commit()
    db.refresh(node)
    return node


def reconcile_gaming_node_drain(db: Session, *, node: Node) -> bool:
    """Advance draining -> maintenance only after all gaming ownership clears."""
    if node.lifecycle_state != "draining":
        return False
    if gaming_node_active_reservation_count(db, node_id=node.id):
        return False
    if gaming_node_inflight_job_count(db, node_id=node.id):
        return False

    # No reservation and no unfinished gaming job means C5/C6 teardown has
    # already proven/released every session that owned capacity.
    from app.services.audit_service import record_audit_event
    node.lifecycle_state = "maintenance"
    node.gaming_accepting_work = False
    record_audit_event(
        db,
        actor_user_id=None,
        action="node.gaming_drain_completed",
        resource_type="node",
        resource_id=str(node.id),
        reason="All gaming reservations and in-flight jobs cleared.",
        details={"old_state": "draining", "new_state": "maintenance"},
    )
    db.flush()
    return True


def queue_gaming_quarantine_recovery(
    db: Session,
    *,
    session: GamingSession,
    source: str,
    actor_user_id: UUID | None = None,
    reason: str = "",
    commit: bool = True,
) -> GamingSession:
    """Queue idempotent runtime sanitization for a quarantined session.

    Recovery never releases capacity directly. It only asks the existing
    gaming.session.delete primitive to produce fresh sanitization evidence.
    The result reconciler remains the sole authority that may repool capacity.
    """

    if source not in {"operator", "automatic"}:
        raise ComputeError("Unsupported quarantine recovery source.")

    if session.status != "quarantined" or session.sanitization_state != "quarantined":
        raise ComputeError("Only quarantined gaming sessions can be recovered.")

    if session.desired_state != "terminated":
        raise ComputeError("Quarantine recovery requires a terminated desired state.")

    if session.node_id is None:
        raise ComputeError("Quarantined gaming session has no assigned node.")

    if session.deployment_mode != "bare_metal":
        raise ComputeError(
            "KG-009C6 quarantine recovery currently applies to bare-metal gaming runtimes."
        )

    reservation = db.scalar(
        select(GamingReservation)
        .where(GamingReservation.gaming_session_id == session.id)
        .with_for_update()
    )
    if reservation is None or reservation.status not in ACTIVE_RESERVATION_STATES:
        raise ComputeError(
            "Quarantine recovery requires the held gaming reservation."
        )

    pending = db.scalar(
        select(NodeJob).where(
            NodeJob.gaming_session_id == session.id,
            NodeJob.status.in_({"pending", "running"}),
        ).limit(1)
    )
    if pending is not None:
        raise ComputeError("Quarantine recovery already has in-flight work.")

    now = datetime.now(UTC)
    session.quarantine_recovery_attempt_count += 1
    session.quarantine_recovery_requested_at = now
    session.quarantine_recovery_last_attempt_at = now
    session.quarantine_recovery_last_source = source
    session.quarantine_recovery_last_message = (reason or "")[:500]
    session.quarantine_recovery_last_evidence = {}
    session.quarantine_recovery_state = "queued"
    session.deployment_stage = "quarantine_recovery_queued"

    db.add(
        NodeJob(
            node_id=session.node_id,
            gaming_session_id=session.id,
            job_type="gaming.session.delete",
            payload={
                "session_id": str(session.id),
                "gpu_uuid": session.gpu_uuid,
                "quarantine_recovery": True,
                "recovery_source": source,
                "recovery_attempt": session.quarantine_recovery_attempt_count,
                "requested_by_user_id": (
                    str(actor_user_id)
                    if actor_user_id is not None
                    else ""
                ),
            },
        )
    )

    if commit:
        db.commit()
        db.refresh(session)
    else:
        db.flush()

    return session


def reconcile_quarantined_gaming_sessions_for_node(
    db: Session,
    *,
    node: Node,
) -> list[UUID]:
    """Automatically retry bounded quarantine remediation on fresh heartbeats."""

    now = datetime.now(UTC)
    if gaming_recovery_readiness_reasons(node, now=now):
        return []

    cutoff = now - timedelta(
        seconds=GAMING_QUARANTINE_AUTO_RECOVERY_COOLDOWN_SECONDS
    )
    queued: list[UUID] = []

    sessions = list(
        db.scalars(
            select(GamingSession).where(
                GamingSession.node_id == node.id,
                GamingSession.status == "quarantined",
                GamingSession.sanitization_state == "quarantined",
                GamingSession.desired_state == "terminated",
            )
        )
    )

    for session in sessions:
        if (
            session.quarantine_recovery_attempt_count
            >= GAMING_QUARANTINE_AUTO_RECOVERY_MAX_ATTEMPTS
        ):
            continue

        if (
            session.quarantine_recovery_last_attempt_at is not None
            and session.quarantine_recovery_last_attempt_at > cutoff
        ):
            continue

        pending = db.scalar(
            select(NodeJob).where(
                NodeJob.gaming_session_id == session.id,
                NodeJob.status.in_({"pending", "running"}),
            ).limit(1)
        )
        if pending is not None:
            continue

        reservation = db.scalar(
            select(GamingReservation).where(
                GamingReservation.gaming_session_id == session.id,
                GamingReservation.status.in_(ACTIVE_RESERVATION_STATES),
            )
        )
        if reservation is None:
            continue

        queue_gaming_quarantine_recovery(
            db,
            session=session,
            source="automatic",
            reason="fresh_heartbeat_auto_remediation",
            commit=False,
        )
        queued.append(session.id)

    return queued


def reconcile_gaming_runtime_health_for_node(
    db: Session,
    *,
    node: Node,
) -> list[UUID]:
    """Fail closed after repeated loss of runtime-critical host readiness.

    Heartbeats can contain a transient bad sample, so a single failed probe
    does not terminate a paying session. Three consecutive heartbeats with a
    critical runtime prerequisite missing cause the existing secure stop
    lifecycle to be requested. The same session row carries the hysteresis
    state, making restart/recovery deterministic without a parallel watchdog
    database.
    """

    now = datetime.now(UTC)
    stopped: list[UUID] = []
    sessions = list(
        db.scalars(
            select(GamingSession).where(
                GamingSession.node_id == node.id,
                GamingSession.status == "running",
                GamingSession.desired_state == "running",
            )
        )
    )
    critical = gaming_runtime_critical_reasons(node, now=now)

    for session in sessions:
        session.runtime_health_last_checked_at = now

        if not critical:
            session.runtime_health_failure_count = 0
            session.runtime_health_last_failure_at = None
            continue

        session.runtime_health_failure_count += 1
        session.runtime_health_last_failure_at = now

        if (
            session.runtime_health_failure_count
            < GAMING_RUNTIME_HEALTH_FAILURE_THRESHOLD
        ):
            continue

        pending = db.scalar(
            select(NodeJob).where(
                NodeJob.gaming_session_id == session.id,
                NodeJob.status.in_({"pending", "running"}),
            ).limit(1)
        )
        if pending is not None:
            continue

        session.failure_category = "runtime_health_lost"
        session.failure_message = (
            "Gaming runtime health failed repeatedly: "
            + ", ".join(critical)
        )[:500]
        queue_gaming_action(
            db,
            session=session,
            action="stop",
            commit=False,
        )
        stopped.append(session.id)

    return stopped


def reconcile_gaming_billing_for_node(
    db: Session,
    *,
    node: Node,
) -> list[UUID]:
    from app.services.gaming_billing_service import (
        reconcile_gaming_billing_for_node as reconcile_finance,
    )

    stop_ids = reconcile_finance(db, node=node)
    for session_id in stop_ids:
        session = db.get(GamingSession, session_id)
        if session is None or session.status != "running":
            continue
        pending = db.scalar(
            select(NodeJob).where(
                NodeJob.gaming_session_id == session.id,
                NodeJob.status.in_({"pending", "running"}),
            ).limit(1)
        )
        if pending is None:
            queue_gaming_action(
                db, session=session, action="stop", commit=False
            )
    return stop_ids


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

    if job.job_type.startswith("gaming.connection."):
        from app.services.gaming_connection_service import (
            finish_connection_job,
        )

        finish_connection_job(
            db,
            job=job,
            status=status,
            result=result,
            error_message=error_message,
        )
        return

    session = db.get(GamingSession, job.gaming_session_id)
    if session is None:
        return

    reservation = db.scalar(
        select(GamingReservation).where(
            GamingReservation.gaming_session_id == session.id
        )
    )

    if job.job_type.startswith("gaming.vm."):
        from app.services.gaming_vm_service import scrub_vm_job_secret
        scrub_vm_job_secret(job)
        if status != "succeeded":
            session.status = "error" if job.job_type != "gaming.vm.create" else "failed"
            session.failure_category = "gaming_vm_job_failed"
            session.failure_message = error_message[:500]
            if job.job_type == "gaming.vm.create":
                if session.usage_reservation_id is not None:
                    from app.services.gaming_billing_service import finalize_gaming_billing
                    finalize_gaming_billing(db, session=session, reason="gaming_vm_create_failed")
                release_gaming_reservation(db, session)
            return
        session.failure_category = ""; session.failure_message = ""
        if job.job_type == "gaming.vm.create":
            session.runtime_id = str(result.get("runtime_id") or "")
            session.guest_vm_id = int(result.get("vmid") or 0) or None
            session.status = "bootstrapping"
            session.deployment_stage = "waiting_for_guest_agent"
            info=dict(session.connection_info or {}); info.update({"hypervisor_runtime_id":session.runtime_id,"guest_vm_id":session.guest_vm_id}); session.connection_info=info
        elif job.job_type == "gaming.vm.start":
            session.status = "bootstrapping"; session.deployment_stage = "waiting_for_guest_agent"
        elif job.job_type == "gaming.vm.stop":
            if session.usage_reservation_id is not None:
                from app.services.gaming_billing_service import finalize_gaming_billing
                finalize_gaming_billing(db, session=session, reason="customer_stop")
            session.status = "stopped"; session.connection_info = {}
        elif job.job_type == "gaming.vm.delete":
            if session.usage_reservation_id is not None:
                from app.services.gaming_billing_service import finalize_gaming_billing
                finalize_gaming_billing(db, session=session, reason="terminated")
            session.status = "terminated"; session.ended_at = datetime.now(UTC); session.connection_info = {}; release_gaming_reservation(db, session)
        return

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
                if session.usage_reservation_id is not None:
                    from app.services.gaming_billing_service import finalize_gaming_billing
                    finalize_gaming_billing(db, session=session, reason="invalid_runtime_result")
                release_gaming_reservation(db, session)
                return

            session.status = "running"
            session.runtime_health_failure_count = 0
            session.runtime_health_last_failure_at = None
            session.deployment_stage = str(
                result.get("deployment_stage")
                or "stream_ready"
            )
            session.runtime_id = runtime_id
            session.connection_info = dict(
                result.get("connection_info") or {}
            )
            session.started_at = datetime.now(UTC)
            if session.usage_reservation_id is not None:
                session.last_metered_at = session.started_at
            if reservation is not None:
                reservation.status = "active"

        elif job.job_type == "gaming.session.start":
            session.status = "running"
            session.runtime_health_failure_count = 0
            session.runtime_health_last_failure_at = None
            session.deployment_stage = str(
                result.get("deployment_stage")
                or "stream_ready"
            )
            session.started_at = session.started_at or datetime.now(UTC)
            if session.usage_reservation_id is not None:
                session.last_metered_at = session.last_metered_at or datetime.now(UTC)
            session.connection_info = dict(
                result.get("connection_info") or {}
            )

        elif job.job_type == "gaming.session.stop":
            from app.services.gaming_billing_service import finalize_gaming_billing
            finalize_gaming_billing(db, session=session, reason="customer_stop")
            session.status = "stopped"
            session.deployment_stage = "stopped"
            session.connection_info = {}

        elif job.job_type == "gaming.session.delete":
            from app.services.gaming_billing_service import finalize_gaming_billing

            now = datetime.now(UTC)
            session.sanitization_attempt_count += 1
            session.sanitization_last_checked_at = now
            sanitation = result.get("sanitization")
            sanitation = sanitation if isinstance(sanitation, dict) else {}

            proof_ok = (
                bool(sanitation.get("sanitized"))
                and bool(sanitation.get("runtime_state_deleted"))
                and int(sanitation.get("paired_clients_remaining") or 0) == 0
                and not bool(sanitation.get("recorded_launcher_alive"))
            )

            node = (
                db.get(Node, session.node_id)
                if session.node_id is not None
                else None
            )
            if node is None:
                readiness_reasons = ["node_missing"]
            elif node.lifecycle_state == "approved":
                # Preserve the frozen C6 repool contract for normal
                # schedulable hosts: sanitization alone is insufficient;
                # the full fresh gaming-host admission gate must pass.
                readiness_reasons = gaming_host_readiness_reasons(node, now=now)
            else:
                # C9 separates recovery permission from placement permission.
                # Draining/maintenance hosts may prove cleanup and release the
                # quarantined reservation without becoming schedulable.
                readiness_reasons = gaming_recovery_readiness_reasons(
                    node,
                    now=now,
                )
            host_revalidated = not readiness_reasons

            recovery_job = bool(
                isinstance(job.payload, dict)
                and job.payload.get("quarantine_recovery")
            )
            evidence = {
                "sanitization": sanitation,
                "host_revalidated": host_revalidated,
                "host_readiness_reasons": readiness_reasons,
                "observed_at": now.isoformat(),
            }
            if recovery_job:
                session.quarantine_recovery_last_evidence = evidence

            finalize_gaming_billing(db, session=session, reason="terminated")
            session.connection_info = {}
            session.ended_at = now

            if not proof_ok or not host_revalidated:
                session.status = "quarantined"
                session.deployment_stage = "quarantined"
                session.sanitization_state = "quarantined"
                if not proof_ok:
                    session.quarantine_reason = (
                        "node_sanitization_proof_missing_or_failed"
                    )
                    session.failure_category = "runtime_sanitization_unproven"
                    session.failure_message = (
                        "Runtime delete completed without authoritative "
                        "sanitization proof; capacity remains quarantined."
                    )
                else:
                    session.quarantine_reason = (
                        "post_sanitization_host_revalidation_failed"
                    )
                    session.failure_category = "runtime_host_revalidation_failed"
                    session.failure_message = (
                        "Runtime sanitization passed but the gaming host "
                        "failed fresh readiness revalidation: "
                        + ", ".join(readiness_reasons)
                    )[:500]

                if recovery_job:
                    session.quarantine_recovery_state = "failed"
                    session.quarantine_recovery_last_message = (
                        session.failure_message
                    )[:500]
                return

            session.status = "terminated"
            session.deployment_stage = "terminated"
            session.sanitization_state = "sanitized"
            session.sanitized_at = now
            session.quarantine_reason = ""
            if recovery_job:
                session.quarantine_recovery_state = "recovered"
                session.quarantine_recovered_at = now
                session.quarantine_recovery_last_message = (
                    "Sanitization and fresh host readiness revalidation passed."
                )
            release_gaming_reservation(db, session)

        return

    session.failure_category = "node_job_failed"
    session.failure_message = error_message[:500]

    if job.job_type == "gaming.session.create":
        if session.usage_reservation_id is not None:
            from app.services.gaming_billing_service import finalize_gaming_billing
            finalize_gaming_billing(db, session=session, reason="runtime_create_failed")
        session.status = "failed"
        session.deployment_stage = "runtime_failed"
        release_gaming_reservation(db, session)
    else:
        # The real machine may still own the runtime/GPU after a failed
        # start/stop/delete operation. Keep the reservation and allow retry.
        if job.job_type == "gaming.session.delete":
            session.status = "quarantined"
            session.deployment_stage = "quarantined"
            session.sanitization_state = "quarantined"
            session.quarantine_reason = "gaming_session_delete_failed"
            session.failure_category = "runtime_sanitization_failed"
            recovery_job = bool(
                isinstance(job.payload, dict)
                and job.payload.get("quarantine_recovery")
            )
            if recovery_job:
                session.quarantine_recovery_state = "failed"
                session.quarantine_recovery_last_message = (
                    error_message or "Quarantine recovery delete job failed."
                )[:500]
                session.quarantine_recovery_last_evidence = {
                    "job_status": status,
                    "error_message": error_message[:500],
                }
        else:
            session.status = "error"
