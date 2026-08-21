from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.compute import GamingReservation, GamingSession, GamingVmBlueprint, NodeCapacity, NodeJob
from app.models.deployment_profile import DeploymentProfile
from app.models.node import Node
from app.services.compute_service import ComputeError, has_capacity
from app.services.deployment_profile_service import create_enrollment_code, hash_enrollment_code

ACTIVE_RESERVATION_STATES = {"reserved", "active"}

def _passthrough_devices(db: Session, node: Node) -> list[dict]:
    root = (node.inventory or {}).get("gpu_passthrough", {})
    devices = root.get("devices", []) if isinstance(root, dict) else []
    profile = db.get(DeploymentProfile, node.deployment_profile_id) if node.deployment_profile_id else None
    policy = profile.resource_policy if profile and isinstance(profile.resource_policy, dict) else {}
    configured_vram = policy.get("gpu_passthrough_vram_mb", {})
    configured_vram = configured_vram if isinstance(configured_vram, dict) else {}
    result = []
    for raw in devices:
        if not isinstance(raw, dict) or not raw.get("assignable"):
            continue
        item = dict(raw)
        slot = str(item.get("slot") or "")
        if not int(item.get("memory_total_mib") or 0):
            try:
                item["memory_total_mib"] = int(configured_vram.get(slot) or 0)
            except (TypeError, ValueError):
                item["memory_total_mib"] = 0
        result.append(item)
    return result

def _reserved_gpu_slots(db: Session, node_id: UUID) -> set[str]:
    sessions = db.scalars(select(GamingSession).where(GamingSession.node_id == node_id, GamingSession.status.notin_({"terminated","failed"})))
    return {str(s.connection_info.get("gpu_pci_slot") or "") for s in sessions if isinstance(s.connection_info, dict)}

def resolve_blueprint(db: Session, slug: str | None) -> GamingVmBlueprint:
    if not slug:
        raise ComputeError("Windows gaming VM deployment requires blueprint_slug.")
    item = db.scalar(select(GamingVmBlueprint).where(GamingVmBlueprint.slug == slug, GamingVmBlueprint.enabled.is_(True)))
    if item is None:
        raise ComputeError(f"Unknown or disabled gaming VM blueprint: {slug}")
    if item.template_vmid < 100:
        raise ComputeError("Gaming VM blueprint has no valid Proxmox template VMID.")
    return item

def select_gaming_hypervisor(db: Session, *, cpu: int, memory_bytes: int, storage_bytes: int, minimum_vram_mb: int):
    rows = db.execute(select(NodeCapacity, Node).join(Node, Node.id == NodeCapacity.node_id).where(Node.lifecycle_state == "approved", Node.is_enabled.is_(True), Node.intended_purpose.in_({"gaming_hypervisor","vps_infrastructure"}), NodeCapacity.virtualization_ready.is_(True), NodeCapacity.execution_enabled.is_(True), NodeCapacity.scheduling_enabled.is_(True)).with_for_update(of=NodeCapacity)).all()
    candidates=[]
    for capacity,node in rows:
        if not has_capacity(capacity,cpu=cpu,memory_bytes=memory_bytes,storage_bytes=storage_bytes):
            continue
        reserved=_reserved_gpu_slots(db,node.id)
        for gpu in _passthrough_devices(db, node):
            slot=str(gpu.get("slot") or "")
            vram=int(gpu.get("memory_total_mib") or 0)
            if slot and slot not in reserved and vram >= minimum_vram_mb:
                candidates.append((vram, capacity.memory_allocatable_bytes-capacity.memory_allocated_bytes, capacity,node,gpu))
    if not candidates:
        raise ComputeError("No gaming hypervisor has free passthrough GPU and requested capacity.")
    candidates.sort(key=lambda x:(x[0],x[1]), reverse=True)
    return candidates[0][2], candidates[0][3], candidates[0][4]

def create_guest_enrollment_profile(db: Session, *, session: GamingSession, hypervisor: Node) -> tuple[DeploymentProfile,str]:
    parent = db.get(DeploymentProfile, hypervisor.deployment_profile_id) if hypervisor.deployment_profile_id else None
    if parent is None:
        raise ComputeError("Gaming hypervisor requires a deployment profile to derive guest control-plane enrollment.")
    code=create_enrollment_code()
    profile=DeploymentProfile(name=f"Gaming guest {str(session.id)[:8]}", purpose="gaming_host", ownership_type="khan_cloud", visibility="internal_only", control_plane_url=parent.control_plane_url, allowed_services={"gaming":True,"gaming_guest":True}, resource_policy={"gaming_session_id":str(session.id),"hypervisor_node_id":str(hypervisor.id),"managed_guest":True,"auto_approve_node":True}, enrollment_code_hash=hash_enrollment_code(code), enrollment_code_prefix=code[:12], expires_at=datetime.now(UTC)+timedelta(minutes=30), max_uses=1, uses_count=0, organization_id=session.organization_id, created_by_user_id=session.created_by_user_id, is_active=True)
    db.add(profile); db.flush(); return profile,code

def queue_windows_vm_create(db: Session, *, session: GamingSession, capacity: NodeCapacity, hypervisor: Node, blueprint: GamingVmBlueprint, gpu: dict) -> None:
    profile,code=create_guest_enrollment_profile(db,session=session,hypervisor=hypervisor)
    session.deployment_stage="vm_queued"
    session.connection_info={"gpu_pci_slot":str(gpu.get("slot") or ""),"guest_profile_id":str(profile.id)}
    db.add(NodeJob(node_id=hypervisor.id,gaming_session_id=session.id,job_type="gaming.vm.create",payload={"session_id":str(session.id),"name":session.name,"template_vmid":blueprint.template_vmid,"storage":blueprint.storage,"bridge":blueprint.bridge,"machine":blueprint.machine,"bios":blueprint.bios,"cpu":session.requested_cpu,"memory_bytes":session.requested_memory_bytes,"storage_bytes":session.requested_storage_bytes,"gpu_pci_slot":str(gpu.get("slot") or ""),"deployment_enrollment_code":code,"control_plane_url":profile.control_plane_url,"guest_profile_id":str(profile.id),"bootstrap_mode":blueprint.bootstrap_mode}))

def scrub_vm_job_secret(job: NodeJob) -> None:
    payload=dict(job.payload or {})
    if "deployment_enrollment_code" in payload:
        payload["deployment_enrollment_code"]="[REDACTED]"
    job.payload=payload

def reconcile_guest_registration(db: Session, *, node: Node) -> None:
    if not node.deployment_profile_id:
        return
    profile=db.get(DeploymentProfile,node.deployment_profile_id)
    policy=profile.resource_policy if profile and isinstance(profile.resource_policy,dict) else {}
    raw=str(policy.get("gaming_session_id") or "")
    try: sid=UUID(raw)
    except ValueError: return
    session=db.get(GamingSession,sid)
    if session is None or session.deployment_mode != "proxmox_windows_vm": return
    session.guest_node_id=node.id
    session.deployment_stage="guest_enrolled"

def reconcile_guest_readiness(db: Session, *, node: Node) -> None:
    sessions=list(db.scalars(select(GamingSession).where(GamingSession.guest_node_id==node.id, GamingSession.deployment_mode=="proxmox_windows_vm", GamingSession.status.in_({"provisioning","bootstrapping"}))))
    if not sessions: return
    from app.services.gaming_service import gaming_host_is_ready
    for session in sessions:
        if gaming_host_is_ready(node):
            session.status="running"
            session.deployment_stage="ready"
            session.started_at=session.started_at or datetime.now(UTC)
            info=dict(session.connection_info or {})
            info.update({"guest_node_id":str(node.id),"guest_ip":node.production_ip or node.management_ip,"protocol":"moonlight"})
            session.connection_info=info
            reservation=db.scalar(select(GamingReservation).where(GamingReservation.gaming_session_id==session.id))
            if reservation is not None: reservation.status="active"
