import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.schemas.node import NodeHeartbeatRequest, NodeRegistrationRequest


def hash_node_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def create_node_secret() -> str:
    return secrets.token_urlsafe(48)


def inventory_summary(inventory: dict) -> dict:
    cpu = inventory.get("cpu", {})
    memory = inventory.get("memory", {})
    docker = inventory.get("docker", {})
    nvidia = inventory.get("nvidia", {})
    gpus = nvidia.get("gpus", []) if isinstance(nvidia, dict) else []

    return {
        "cpu_model": str(cpu.get("model", "")),
        "cpu_logical_count": int(cpu.get("logical_count", 0) or 0),
        "memory_total_bytes": int(memory.get("total_bytes", 0) or 0),
        "docker_available": bool(docker.get("available", False)),
        "nvidia_available": bool(nvidia.get("available", False)),
        "gpu_count": len(gpus),
    }


def register_node(
    db: Session,
    payload: NodeRegistrationRequest,
) -> tuple[Node, str]:
    node = db.scalar(select(Node).where(Node.machine_id == payload.machine_id))
    node_secret = create_node_secret()
    summary = inventory_summary(payload.inventory)

    if node is None:
        node = Node(
            name=payload.name,
            machine_id=payload.machine_id,
            secret_hash=hash_node_secret(node_secret),
            status="online",
            is_enabled=True,
            hostname=payload.hostname,
            operating_system=payload.operating_system,
            kernel_version=payload.kernel_version,
            agent_version=payload.agent_version,
            management_ip=payload.management_ip,
            production_ip=payload.production_ip,
            inventory=payload.inventory,
            last_seen_at=datetime.now(UTC),
            **summary,
        )
        db.add(node)
    else:
        node.name = payload.name
        node.secret_hash = hash_node_secret(node_secret)
        node.status = "online"
        node.hostname = payload.hostname
        node.operating_system = payload.operating_system
        node.kernel_version = payload.kernel_version
        node.agent_version = payload.agent_version
        node.management_ip = payload.management_ip
        node.production_ip = payload.production_ip
        node.inventory = payload.inventory
        node.last_seen_at = datetime.now(UTC)
        for key, value in summary.items():
            setattr(node, key, value)

    db.commit()
    db.refresh(node)
    return node, node_secret


def authenticate_node(db: Session, node_id, node_secret: str) -> Node | None:
    node = db.get(Node, node_id)
    if node is None:
        return None
    expected = node.secret_hash
    supplied = hash_node_secret(node_secret)
    if not secrets.compare_digest(expected, supplied):
        return None
    return node


def heartbeat_node(
    db: Session,
    node: Node,
    payload: NodeHeartbeatRequest,
) -> Node:
    summary = inventory_summary(payload.inventory)
    node.status = "online"
    node.hostname = payload.hostname
    node.operating_system = payload.operating_system
    node.kernel_version = payload.kernel_version
    node.agent_version = payload.agent_version
    node.management_ip = payload.management_ip
    node.production_ip = payload.production_ip
    node.inventory = payload.inventory
    node.last_seen_at = datetime.now(UTC)
    for key, value in summary.items():
        setattr(node, key, value)

    db.commit()
    db.refresh(node)
    return node
