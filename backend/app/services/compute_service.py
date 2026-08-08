from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compute import NodeCapacity, NodeJob, ProvisioningAuthorization, ResourceReservation, VPSInstance
from app.models.node import Node
from app.models.user import User
from app.schemas.compute import CapacityRead, ComputeHostRead, VPSCreate, VPSImageRead
from app.services.audit_service import record_audit_event
from app.services.organization_service import user_can_access_organization, visible_organizations
from app.services.rbac_service import get_role_names

GIB = 1024 ** 3
STAFF_ROLES = {"platform_owner", "platform_admin", "operator"}
TERMINAL_VPS_STATES = {"deleted", "failed"}
ACTIVE_RESERVATION_STATES = {"reserved", "active"}
SUPPORTED_VPS_IMAGES = {
    "ubuntu-24.04": VPSImageRead(
        slug="ubuntu-24.04", name="Ubuntu 24.04 LTS", operating_system="ubuntu",
        version="24.04", access_username="ubuntu", supports_cloud_init=True,
    ),
}


class ComputeError(ValueError):
    pass


def _safe_int(value, default: int = 0) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return default


def _virtualization_inventory(node: Node) -> dict:
    inv = node.inventory or {}
    raw = inv.get("virtualization", {})
    return raw if isinstance(raw, dict) else {}


def _storage_total(node: Node) -> int:
    inv = node.inventory or {}
    fs = inv.get("filesystem", {})
    if not isinstance(fs, dict):
        return 0
    # v1 intentionally uses only the root filesystem. Dedicated VPS pools are
    # added later and are never inferred from Docker storage.
    return _safe_int(fs.get("root_total_bytes"))


def calculate_host_reserve(cpu_total: int, memory_total: int, storage_total: int) -> tuple[int, int, int]:
    cpu_reserved = min(cpu_total, max(2, math.ceil(cpu_total * 0.0625))) if cpu_total else 0
    memory_reserved = min(memory_total, max(2 * GIB, math.ceil(memory_total * 0.125))) if memory_total else 0
    storage_reserved = min(storage_total, max(20 * GIB, math.ceil(storage_total * 0.10))) if storage_total else 0
    return cpu_reserved, memory_reserved, storage_reserved


def readiness_reasons(node: Node, capacity: NodeCapacity) -> list[str]:
    reasons: list[str] = []
    if node.lifecycle_state != "approved":
        reasons.append("node_not_approved")
    if node.connectivity_state != "online":
        reasons.append("node_not_online")
    if node.intended_purpose != "vps_infrastructure":
        reasons.append("node_not_vps_infrastructure")
    if not capacity.kvm_available:
        reasons.append("kvm_unavailable")
    if not capacity.libvirt_available:
        reasons.append("libvirt_unavailable")
    if not capacity.execution_enabled:
        reasons.append("vps_execution_disabled")
    if capacity.cpu_allocatable <= 0:
        reasons.append("cpu_unavailable")
    if capacity.memory_allocatable_bytes <= 0:
        reasons.append("memory_unavailable")
    if capacity.storage_allocatable_bytes <= 0:
        reasons.append("storage_unavailable")
    return reasons


def sync_node_capacity(db: Session, node: Node, *, commit: bool = True) -> NodeCapacity:
    capacity = db.scalar(select(NodeCapacity).where(NodeCapacity.node_id == node.id))
    if capacity is None:
        capacity = NodeCapacity(node_id=node.id)
        db.add(capacity)
        db.flush()

    cpu_total = _safe_int(node.cpu_logical_count)
    memory_total = _safe_int(node.memory_total_bytes)
    storage_total = _storage_total(node)
    cpu_res, mem_res, storage_res = calculate_host_reserve(cpu_total, memory_total, storage_total)
    virt = _virtualization_inventory(node)

    capacity.cpu_total = cpu_total
    capacity.cpu_reserved_host = cpu_res
    capacity.cpu_allocatable = max(0, cpu_total - cpu_res)
    capacity.memory_total_bytes = memory_total
    capacity.memory_reserved_host_bytes = mem_res
    capacity.memory_allocatable_bytes = max(0, memory_total - mem_res)
    capacity.storage_total_bytes = storage_total
    capacity.storage_reserved_host_bytes = storage_res
    capacity.storage_allocatable_bytes = max(0, storage_total - storage_res)
    capacity.kvm_available = bool(virt.get("kvm_available", False))
    capacity.libvirt_available = bool(virt.get("libvirt_available", False))
    capacity.virtualization_ready = bool(capacity.kvm_available and capacity.libvirt_available)
    capacity.execution_enabled = bool(virt.get("execution_enabled", False))
    capacity.last_refreshed_at = datetime.now(UTC)
    capacity.scheduling_enabled = not readiness_reasons(node, capacity)

    if commit:
        db.commit(); db.refresh(capacity)
    else:
        db.flush()
    return capacity


def capacity_read(node: Node, capacity: NodeCapacity) -> CapacityRead:
    return CapacityRead(
        node_id=node.id,
        cpu_total=capacity.cpu_total,
        cpu_reserved_host=capacity.cpu_reserved_host,
        cpu_allocatable=capacity.cpu_allocatable,
        cpu_allocated=capacity.cpu_allocated,
        cpu_available=max(0, capacity.cpu_allocatable - capacity.cpu_allocated),
        memory_total_bytes=capacity.memory_total_bytes,
        memory_reserved_host_bytes=capacity.memory_reserved_host_bytes,
        memory_allocatable_bytes=capacity.memory_allocatable_bytes,
        memory_allocated_bytes=capacity.memory_allocated_bytes,
        memory_available_bytes=max(0, capacity.memory_allocatable_bytes - capacity.memory_allocated_bytes),
        storage_total_bytes=capacity.storage_total_bytes,
        storage_reserved_host_bytes=capacity.storage_reserved_host_bytes,
        storage_allocatable_bytes=capacity.storage_allocatable_bytes,
        storage_allocated_bytes=capacity.storage_allocated_bytes,
        storage_available_bytes=max(0, capacity.storage_allocatable_bytes - capacity.storage_allocated_bytes),
        kvm_available=capacity.kvm_available,
        libvirt_available=capacity.libvirt_available,
        virtualization_ready=capacity.virtualization_ready,
        execution_enabled=capacity.execution_enabled,
        scheduling_enabled=capacity.scheduling_enabled,
        readiness_reasons=readiness_reasons(node, capacity),
        last_refreshed_at=capacity.last_refreshed_at,
    )


def list_compute_hosts(db: Session) -> list[ComputeHostRead]:
    nodes = list(db.scalars(select(Node).where(Node.intended_purpose == "vps_infrastructure").order_by(Node.name)).unique())
    result: list[ComputeHostRead] = []
    for node in nodes:
        cap = sync_node_capacity(db, node, commit=False)
        result.append(ComputeHostRead(
            node_id=node.id, name=node.name, hostname=node.hostname,
            connectivity_state=node.connectivity_state, lifecycle_state=node.lifecycle_state,
            intended_purpose=node.intended_purpose, capacity=capacity_read(node, cap),
        ))
    db.commit()
    return result


def _resolve_organization(db: Session, user: User, requested: UUID | None) -> UUID:
    if requested is not None:
        if not user_can_access_organization(db, user, requested):
            raise ComputeError("Organization is not accessible.")
        return requested
    organizations = visible_organizations(db, user)
    if len(organizations) == 1:
        return organizations[0].id
    raise ComputeError("organization_id is required when more than one organization is visible.")


def has_capacity(capacity: NodeCapacity, *, cpu: int, memory_bytes: int, storage_bytes: int) -> bool:
    return (
        capacity.cpu_allocatable - capacity.cpu_allocated >= cpu
        and capacity.memory_allocatable_bytes - capacity.memory_allocated_bytes >= memory_bytes
        and capacity.storage_allocatable_bytes - capacity.storage_allocated_bytes >= storage_bytes
    )


def _candidate_query(db: Session):
    return (
        select(NodeCapacity, Node)
        .join(Node, Node.id == NodeCapacity.node_id)
        .where(NodeCapacity.scheduling_enabled.is_(True))
        .where(Node.lifecycle_state == "approved")
        .where(Node.connectivity_state == "online")
        .where(Node.intended_purpose == "vps_infrastructure")
        .with_for_update(of=NodeCapacity)
    )


def select_host(db: Session, *, cpu: int, memory_bytes: int, storage_bytes: int) -> tuple[NodeCapacity, Node]:
    candidates: list[tuple[NodeCapacity, Node]] = []
    for capacity, node in db.execute(_candidate_query(db)).all():
        if not has_capacity(
            capacity, cpu=cpu, memory_bytes=memory_bytes, storage_bytes=storage_bytes
        ):
            continue
        candidates.append((capacity, node))
    if not candidates:
        raise ComputeError(
            "No VPS host is currently schedulable with the requested CPU, memory and storage. "
            "Check host virtualization readiness and available capacity."
        )
    # Prefer the host with the most available memory, then CPU. This simple
    # deterministic policy is intentionally replaceable by the intelligent scheduler later.
    candidates.sort(
        key=lambda item: (
            item[0].memory_allocatable_bytes - item[0].memory_allocated_bytes,
            item[0].cpu_allocatable - item[0].cpu_allocated,
        ),
        reverse=True,
    )
    return candidates[0]



def list_vps_images() -> list[VPSImageRead]:
    return list(SUPPORTED_VPS_IMAGES.values())


def _validate_ssh_public_key(value: str) -> tuple[str, str]:
    import base64, hashlib
    key = value.strip()
    if "\n" in key or "\r" in key:
        raise ComputeError("SSH public key must be a single line.")
    parts = key.split()
    allowed = {"ssh-ed25519","ssh-rsa","ecdsa-sha2-nistp256","ecdsa-sha2-nistp384","ecdsa-sha2-nistp521"}
    if len(parts) < 2 or parts[0] not in allowed:
        raise ComputeError("Unsupported SSH public key format.")
    try:
        raw = base64.b64decode(parts[1].encode("ascii"), validate=True)
    except Exception as exc:
        raise ComputeError("SSH public key is not valid base64.") from exc
    fp = "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
    return key, fp


def _resolve_provisioning_authorization(db: Session, *, actor: User, organization_id: UUID, requested_id: UUID | None) -> ProvisioningAuthorization:
    auth = db.get(ProvisioningAuthorization, requested_id) if requested_id else None
    if auth is None:
        if not (actor.is_superuser or STAFF_ROLES.intersection(get_role_names(actor))):
            raise ComputeError("Provisioning authorization is required before customer resources can be reserved.")
        auth = ProvisioningAuthorization(
            organization_id=organization_id, created_by_user_id=actor.id,
            source="operator", status="authorized", reference_type="internal",
            reference_id="operator-approved", expires_at=datetime.now(UTC)+timedelta(hours=1),
        )
        db.add(auth); db.flush()
    if auth.organization_id != organization_id or auth.status != "authorized" or auth.consumed_at is not None:
        raise ComputeError("Provisioning authorization is not usable.")
    if auth.expires_at is not None:
        expiry = auth.expires_at if auth.expires_at.tzinfo else auth.expires_at.replace(tzinfo=UTC)
        if expiry <= datetime.now(UTC):
            raise ComputeError("Provisioning authorization has expired.")
    return auth


def create_vps(db: Session, *, payload: VPSCreate, actor: User) -> VPSInstance:
    org_id = _resolve_organization(db, actor, payload.organization_id)
    image = SUPPORTED_VPS_IMAGES.get(payload.image)
    if image is None:
        raise ComputeError("Unsupported VPS image.")
    ssh_public_key, ssh_fingerprint = _validate_ssh_public_key(payload.ssh_public_key)
    authorization = _resolve_provisioning_authorization(
        db, actor=actor, organization_id=org_id, requested_id=payload.provisioning_authorization_id
    )
    memory_bytes = payload.memory_mb * 1024 ** 2
    disk_bytes = payload.disk_gb * GIB

    capacity, node = select_host(
        db, cpu=payload.vcpu, memory_bytes=memory_bytes, storage_bytes=disk_bytes
    )

    vps = VPSInstance(
        organization_id=org_id, node_id=node.id, created_by_user_id=actor.id,
        provisioning_authorization_id=authorization.id,
        name=payload.name, image=payload.image, vcpu=payload.vcpu,
        memory_bytes=memory_bytes, disk_bytes=disk_bytes,
        status="provisioning", desired_state="running",
        access_username=image.access_username, ssh_public_key_fingerprint=ssh_fingerprint,
    )
    db.add(vps); db.flush()

    reservation = ResourceReservation(
        vps_instance_id=vps.id, node_id=node.id, cpu=payload.vcpu,
        memory_bytes=memory_bytes, storage_bytes=disk_bytes, status="reserved",
    )
    db.add(reservation)
    capacity.cpu_allocated += payload.vcpu
    capacity.memory_allocated_bytes += memory_bytes
    capacity.storage_allocated_bytes += disk_bytes

    db.add(NodeJob(
        node_id=node.id, vps_instance_id=vps.id, job_type="vps.create",
        payload={
            "vps_id": str(vps.id), "name": vps.name, "image": vps.image,
            "vcpu": vps.vcpu, "memory_bytes": vps.memory_bytes,
            "disk_bytes": vps.disk_bytes,
            "access_username": image.access_username,
            "ssh_public_key": ssh_public_key,
        },
    ))
    authorization.status = "consumed"
    authorization.consumed_at = datetime.now(UTC)
    record_audit_event(
        db, actor_user_id=actor.id, action="vps.created",
        resource_type="vps_instance", resource_id=str(vps.id),
        details={"node_id": str(node.id), "vcpu": vps.vcpu, "memory_bytes": memory_bytes, "disk_bytes": disk_bytes},
    )
    db.commit(); db.refresh(vps)
    return vps


def visible_vps(db: Session, user: User) -> list[VPSInstance]:
    items = list(db.scalars(select(VPSInstance).order_by(VPSInstance.created_at.desc())).unique())
    if user.is_superuser or STAFF_ROLES.intersection(get_role_names(user)):
        return items
    return [item for item in items if user_can_access_organization(db, user, item.organization_id)]


def get_visible_vps(db: Session, user: User, vps_id: UUID) -> VPSInstance:
    vps = db.get(VPSInstance, vps_id)
    if vps is None:
        raise ComputeError("VPS not found.")
    if not user_can_access_organization(db, user, vps.organization_id):
        raise ComputeError("VPS not found.")
    return vps


def queue_vps_action(db: Session, *, vps: VPSInstance, action: str, actor: User) -> VPSInstance:
    mapping = {"start": "vps.start", "stop": "vps.stop", "reboot": "vps.reboot", "delete": "vps.delete"}
    if action not in mapping:
        raise ComputeError("Unsupported VPS action.")
    if vps.status == "deleted":
        raise ComputeError("Deleted VPS cannot receive actions.")
    if vps.node_id is None:
        raise ComputeError("VPS is not assigned to a node.")
    db.add(NodeJob(
        node_id=vps.node_id, vps_instance_id=vps.id, job_type=mapping[action],
        payload={"vps_id": str(vps.id), "runtime_id": vps.runtime_id, "name": vps.name},
    ))
    vps.desired_state = "deleted" if action == "delete" else ("running" if action in {"start", "reboot"} else "stopped")
    record_audit_event(db, actor_user_id=actor.id, action=mapping[action], resource_type="vps_instance", resource_id=str(vps.id))
    db.commit(); db.refresh(vps)
    return vps


def release_reservation(db: Session, vps: VPSInstance) -> None:
    reservation = db.scalar(select(ResourceReservation).where(ResourceReservation.vps_instance_id == vps.id))
    if reservation is None or reservation.status not in ACTIVE_RESERVATION_STATES:
        return
    capacity = db.scalar(select(NodeCapacity).where(NodeCapacity.node_id == reservation.node_id).with_for_update())
    if capacity is not None:
        capacity.cpu_allocated = max(0, capacity.cpu_allocated - reservation.cpu)
        capacity.memory_allocated_bytes = max(0, capacity.memory_allocated_bytes - reservation.memory_bytes)
        capacity.storage_allocated_bytes = max(0, capacity.storage_allocated_bytes - reservation.storage_bytes)
    reservation.status = "released"
    reservation.released_at = datetime.now(UTC)


def claim_next_job(db: Session, node: Node) -> NodeJob | None:
    job = db.scalar(
        select(NodeJob)
        .where(NodeJob.node_id == node.id, NodeJob.status == "pending")
        .order_by(NodeJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "running"; job.claimed_at = datetime.now(UTC); job.attempt_count += 1
    db.commit(); db.refresh(job)
    return job


def finish_job(db: Session, *, node: Node, job_id: UUID, status: str, result: dict, error_message: str) -> NodeJob:
    job = db.get(NodeJob, job_id)
    if job is None or job.node_id != node.id:
        raise ComputeError("Node job not found.")
    if job.status not in {"running", "pending"}:
        return job
    job.status = status; job.result = result; job.error_message = error_message[:500]; job.completed_at = datetime.now(UTC)
    if job.vps_instance_id is not None:
        vps = db.get(VPSInstance, job.vps_instance_id)
        if vps is not None:
            if status == "succeeded":
                if job.job_type == "vps.create":
                    vps.status = "running"; vps.runtime_id = str(result.get("runtime_id", "")); vps.primary_ip = str(result.get("primary_ip", ""))
                    vps.access_username = str(result.get("access_username", vps.access_username or "ubuntu"))
                    if bool(result.get("guest_ready", False)): vps.guest_ready_at = datetime.now(UTC)
                    reservation = db.scalar(select(ResourceReservation).where(ResourceReservation.vps_instance_id == vps.id))
                    if reservation is not None: reservation.status = "active"
                elif job.job_type == "vps.start": vps.status = "running"
                elif job.job_type == "vps.stop": vps.status = "stopped"
                elif job.job_type == "vps.reboot": vps.status = "running"
                elif job.job_type == "vps.delete":
                    vps.status = "deleted"; release_reservation(db, vps)
            else:
                vps.status = "failed"; vps.failure_category = "node_job_failed"; vps.failure_message = error_message[:500]
                if job.job_type == "vps.create": release_reservation(db, vps)
    db.commit(); db.refresh(job)
    return job
