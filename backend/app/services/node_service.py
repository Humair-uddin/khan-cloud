import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.node import Node
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

def register_node(db: Session, payload: NodeRegistrationRequest) -> tuple[Node,str]:
    node=db.scalar(select(Node).where(Node.machine_id==payload.machine_id))
    secret=create_node_secret(); summary=inventory_summary(payload.inventory)
    caps=normalized_capabilities(payload.capabilities,payload.inventory)
    if node is None:
        node=Node(
            name=payload.name,machine_id=payload.machine_id,secret_hash=hash_node_secret(secret),
            status="pending_approval",lifecycle_state="pending_approval",connectivity_state="online",
            marketplace_state="not_eligible",is_enabled=True,capabilities=caps,
            hostname=payload.hostname,operating_system=payload.operating_system,
            kernel_version=payload.kernel_version,agent_version=payload.agent_version,
            management_ip=payload.management_ip,production_ip=payload.production_ip,
            inventory=payload.inventory,last_seen_at=datetime.now(UTC),**summary,
        )
        db.add(node); db.flush()
        record_audit_event(db,actor_user_id=None,action="node.registered",
            resource_type="node",resource_id=str(node.id),
            details={"machine_id":node.machine_id,"name":node.name})
    else:
        if node.lifecycle_state=="retired": raise NodeLifecycleError("Retired nodes cannot re-enroll.")
        node.name=payload.name; node.secret_hash=hash_node_secret(secret)
        node.connectivity_state="online"; node.hostname=payload.hostname
        node.operating_system=payload.operating_system; node.kernel_version=payload.kernel_version
        node.agent_version=payload.agent_version; node.management_ip=payload.management_ip
        node.production_ip=payload.production_ip; node.inventory=payload.inventory
        node.capabilities=caps; node.last_seen_at=datetime.now(UTC)
        for k,v in summary.items(): setattr(node,k,v)
        sync_legacy_status(node)
    db.commit(); db.refresh(node); return node,secret

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
