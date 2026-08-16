import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.node import Node
from app.models.physical_host import PhysicalHost
from app.schemas.node import NodeHeartbeatRequest, NodeRegistrationRequest
from app.services.audit_service import record_audit_event

LIFECYCLE_STATES = {"pending_approval","approved","rejected","maintenance","disabled","retired"}
ALLOWED_TRANSITIONS = {
    "pending_approval": {"approved","rejected","disabled"},
    "approved": {"maintenance","disabled","retired"},
    "rejected": {"pending_approval","retired"},
    "maintenance": {"approved","disabled","retired"},
    "disabled": {"approved","retired"},
    "retired": set(),
}
class NodeLifecycleError(ValueError): pass

def hash_node_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()

def create_node_secret() -> str:
    return secrets.token_urlsafe(48)

def inventory_summary(inventory: dict) -> dict:
    cpu=inventory.get("cpu",{}); memory=inventory.get("memory",{})
    docker=inventory.get("docker",{}); nvidia=inventory.get("nvidia",{})
    gpus=nvidia.get("gpus",[]) if isinstance(nvidia,dict) else []
    return {
        "cpu_model": str(cpu.get("model","")),
        "cpu_logical_count": int(cpu.get("logical_count",0) or 0),
        "memory_total_bytes": int(memory.get("total_bytes",0) or 0),
        "docker_available": bool(docker.get("available",False)),
        "nvidia_available": bool(nvidia.get("available",False)),
        "gpu_count": len(gpus),
    }

def normalized_capabilities(payload_capabilities: dict, inventory: dict) -> dict:
    s=inventory_summary(inventory); c=dict(payload_capabilities or {})
    c.setdefault("docker",s["docker_available"]); c.setdefault("gpu",s["gpu_count"]>0)
    c.setdefault("linux",True); c.setdefault("windows",False)
    c.setdefault("gaming",False); c.setdefault("ai_compute",False)
    c.setdefault("virtualization",False); c.setdefault("storage",False); c.setdefault("streaming",False)
    return c

def sync_legacy_status(node: Node) -> None:
    if node.lifecycle_state in {"disabled","rejected","retired"}: node.status=node.lifecycle_state
    elif node.connectivity_state=="online": node.status="online"
    elif node.lifecycle_state=="pending_approval": node.status="pending_approval"
    else: node.status="offline"

def _purpose_code(purpose: str) -> str:
    return {"gaming_host":"GAME","vps_host":"VPS","ai_compute":"GPU","internal_lab":"LAB"}.get(purpose, "NODE")

def _host_suffix(host: PhysicalHost) -> str:
    serial = "".join(ch for ch in (host.serial_number or "").upper() if ch.isalnum())
    return (serial[-8:] if serial else host.fingerprint[:8].upper())

def _assigned_name(host: PhysicalHost, purpose: str, generation: int) -> str:
    return f"KC-{_purpose_code(purpose)}-{_host_suffix(host)}-{generation:02d}"

def _resolve_physical_host(db: Session, payload: NodeRegistrationRequest, organization_id: UUID | None) -> PhysicalHost:
    hw = payload.hardware_identity
    fingerprint = (hw.fingerprint or "").strip().lower()
    if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
        raise NodeLifecycleError("Strong physical-host identity is required for enrollment.")
    host = db.scalar(select(PhysicalHost).where(PhysicalHost.fingerprint == fingerprint))
    if host is None:
        host = PhysicalHost(
            organization_id=organization_id, fingerprint=fingerprint,
            system_uuid=hw.system_uuid.strip(), serial_number=hw.serial_number.strip(),
            manufacturer=hw.manufacturer.strip(), model=hw.model.strip(),
            trust_state="observed", deployment_generation=0, last_seen_at=datetime.now(UTC),
        )
        db.add(host); db.flush()
        record_audit_event(db, actor_user_id=None, action="physical_host.discovered",
            resource_type="physical_host", resource_id=str(host.id),
            details={"serial_number": host.serial_number, "manufacturer": host.manufacturer, "model": host.model})
    elif host.organization_id is not None and organization_id is not None and host.organization_id != organization_id:
        raise NodeLifecycleError("Physical host is already bound to another organization.")
    elif host.organization_id is None and organization_id is not None:
        host.organization_id = organization_id
    # A matching hash is not authentication; the valid one-time deployment profile is.
    # Evidence changes are retained only when non-empty and fingerprint remains identical.
    host.system_uuid = hw.system_uuid.strip() or host.system_uuid
    host.serial_number = hw.serial_number.strip() or host.serial_number
    host.manufacturer = hw.manufacturer.strip() or host.manufacturer
    host.model = hw.model.strip() or host.model
    host.last_seen_at = datetime.now(UTC)
    return host

def register_node(
    db: Session, payload: NodeRegistrationRequest, *, deployment_profile_id: UUID | None = None,
    intended_purpose: str | None = None, organization_id: UUID | None = None, commit: bool = True,
) -> tuple[Node, str]:
    # Enrollment authorization is enforced by the API before this service is called.
    existing = db.scalar(select(Node).where(Node.machine_id == payload.machine_id))
    secret = create_node_secret(); summary = inventory_summary(payload.inventory)
    caps = normalized_capabilities(payload.capabilities, payload.inventory)
    purpose = intended_purpose or "internal_lab"
    host = _resolve_physical_host(db, payload, organization_id)
    if existing is not None:
        if existing.physical_host_id not in {None, host.id}:
            raise NodeLifecycleError("Deployment identity conflicts with physical host identity.")
        if existing.lifecycle_state == "retired":
            raise NodeLifecycleError("Retired deployment identities cannot re-enroll.")
        node = existing
        node.physical_host_id = host.id
        generation = max(node.deployment_generation or 1, host.deployment_generation or 0)
        host.deployment_generation = generation
    else:
        host.deployment_generation = int(host.deployment_generation or 0) + 1
        generation = host.deployment_generation
        node = Node(
            name=_assigned_name(host, purpose, generation), machine_id=payload.machine_id,
            physical_host_id=host.id, deployment_generation=generation,
            secret_hash=hash_node_secret(secret), status="pending_approval", lifecycle_state="pending_approval",
            connectivity_state="online", marketplace_state="not_eligible", is_enabled=True, capabilities=caps,
            deployment_profile_id=deployment_profile_id, intended_purpose=purpose, hostname=payload.hostname,
            operating_system=payload.operating_system, kernel_version=payload.kernel_version,
            agent_version=payload.agent_version, management_ip=payload.management_ip,
            production_ip=payload.production_ip, inventory=payload.inventory, last_seen_at=datetime.now(UTC), **summary,
        )
        # Authorized redeployment supersedes previous non-retired deployments of this same physical host.
        previous = list(
            db.scalars(
                select(Node).where(
                    Node.physical_host_id == host.id,
                    Node.id != node.id,
                    Node.intended_purpose == purpose,
                )
            ).all()
        )
        db.add(node); db.flush()
        for old in previous:
            if old.superseded_by_node_id is None and old.lifecycle_state != "retired":
                old.superseded_by_node_id = node.id; old.lifecycle_state = "disabled"; old.is_enabled = False
                old.connectivity_state = "offline"; old.marketplace_state = "not_eligible"; sync_legacy_status(old)
                record_audit_event(db, actor_user_id=None, action="node.superseded", resource_type="node",
                    resource_id=str(old.id), details={"replacement_node_id": str(node.id), "physical_host_id": str(host.id)})
        record_audit_event(db, actor_user_id=None, action="node.registered", resource_type="node",
            resource_id=str(node.id), details={"machine_id":node.machine_id,"name":node.name,
            "physical_host_id":str(host.id),"deployment_generation":generation})
    node.secret_hash=hash_node_secret(secret); node.deployment_profile_id=deployment_profile_id or node.deployment_profile_id
    node.intended_purpose=purpose; node.connectivity_state="online"; node.hostname=payload.hostname
    node.operating_system=payload.operating_system; node.kernel_version=payload.kernel_version
    node.agent_version=payload.agent_version; node.management_ip=payload.management_ip; node.production_ip=payload.production_ip
    node.inventory=payload.inventory; node.capabilities=caps; node.last_seen_at=datetime.now(UTC)
    for k,v in summary.items(): setattr(node,k,v)
    sync_legacy_status(node)
    if commit: db.commit(); db.refresh(node)
    else: db.flush()
    return node, secret

def authenticate_node(db: Session,node_id,node_secret: str) -> Node | None:
    node=db.get(Node,node_id)
    if node is None: return None
    if not secrets.compare_digest(node.secret_hash,hash_node_secret(node_secret)): return None
    return node

def heartbeat_node(db: Session,node: Node,payload: NodeHeartbeatRequest) -> Node:
    if node.lifecycle_state in {"disabled","rejected","retired"}:
        raise NodeLifecycleError(f"Heartbeat denied while node lifecycle is {node.lifecycle_state}.")
    summary=inventory_summary(payload.inventory)
    node.connectivity_state="online"; node.hostname=payload.hostname
    node.operating_system=payload.operating_system; node.kernel_version=payload.kernel_version
    node.agent_version=payload.agent_version; node.management_ip=payload.management_ip
    node.production_ip=payload.production_ip; node.inventory=payload.inventory
    node.capabilities=normalized_capabilities(payload.capabilities,payload.inventory)
    node.last_seen_at=datetime.now(UTC)
    for k,v in summary.items(): setattr(node,k,v)
    sync_legacy_status(node); db.commit(); db.refresh(node); return node

def transition_node(db: Session,*,node: Node,new_state: str,actor_user_id: UUID,reason: str="") -> Node:
    current=node.lifecycle_state
    if new_state not in LIFECYCLE_STATES: raise NodeLifecycleError(f"Unknown lifecycle state: {new_state}")
    if new_state not in ALLOWED_TRANSITIONS.get(current,set()):
        raise NodeLifecycleError(f"Invalid lifecycle transition: {current} -> {new_state}")
    node.lifecycle_state=new_state
    if new_state=="approved": node.is_enabled=True
    elif new_state in {"disabled","rejected","retired"}:
        node.is_enabled=False; node.marketplace_state="not_eligible"
    sync_legacy_status(node)
    record_audit_event(db,actor_user_id=actor_user_id,action=f"node.{new_state}",
        resource_type="node",resource_id=str(node.id),reason=reason,
        details={"old_state":current,"new_state":new_state})
    db.commit(); db.refresh(node); return node


def auto_approve_enrolled_node(db: Session, node: Node) -> None:
    if node.lifecycle_state != "pending_approval":
        return
    node.lifecycle_state = "approved"
    node.is_enabled = True
    sync_legacy_status(node)
    record_audit_event(
        db, actor_user_id=None, action="node.auto_approved",
        resource_type="node", resource_id=str(node.id),
        reason="Scoped deployment policy authorized automatic approval.",
        details={"deployment_profile_id": str(node.deployment_profile_id)},
    )
    db.flush()
