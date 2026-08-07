from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment_profile import DeploymentProfile
from app.models.node import Node
from app.schemas.deployment_operations import (
    DeploymentOperationsSummary,
    NodeOperationsStatus,
)


SUCCESS_STATUSES = {"success", "completed"}
FAILURE_STATUSES = {
    "failed",
    "dependency_blocked",
    "compatibility_blocked",
    "rollback_failed",
}
ACTIVE_INSTALL_STATUSES = {
    "running",
    "installing",
    "preflight",
    "remediating",
    "recovering",
}


def effective_connectivity(
    node: Node,
    *,
    now: datetime,
    stale_after_seconds: int,
) -> str:
    if node.last_seen_at is None:
        return "offline"

    cutoff = now - timedelta(seconds=stale_after_seconds)
    seen = node.last_seen_at
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=UTC)

    if seen < cutoff:
        return "stale"

    if node.connectivity_state in {"offline", "disabled"}:
        return node.connectivity_state

    return "online"


def node_operations_status(
    node: Node,
    *,
    now: datetime,
    stale_after_seconds: int,
) -> NodeOperationsStatus:
    connectivity = effective_connectivity(
        node,
        now=now,
        stale_after_seconds=stale_after_seconds,
    )

    support_attention = False
    support_reason = ""

    if node.lifecycle_state in {"rejected", "disabled", "retired"}:
        support_attention = False
    elif node.installation_status in FAILURE_STATUSES:
        support_attention = True
        support_reason = (
            node.installation_failure_category
            or f"installation_{node.installation_status}"
        )
    elif connectivity in {"offline", "stale"}:
        support_attention = True
        support_reason = f"node_{connectivity}"

    return NodeOperationsStatus(
        node_id=node.id,
        name=node.name,
        lifecycle_state=node.lifecycle_state,
        connectivity_state=node.connectivity_state,
        effective_connectivity=connectivity,
        last_seen_at=node.last_seen_at,
        installation_status=node.installation_status,
        installation_stage=node.installation_stage,
        installation_failure_category=node.installation_failure_category,
        installation_message=node.installation_message,
        installation_updated_at=node.installation_updated_at,
        support_attention=support_attention,
        support_reason=support_reason,
    )


def build_deployment_operations_summary(
    profile: DeploymentProfile,
    nodes: list[Node],
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 300,
) -> DeploymentOperationsSummary:
    if stale_after_seconds < 30:
        raise ValueError("stale_after_seconds must be at least 30.")

    current = now or datetime.now(UTC)
    statuses = [
        node_operations_status(
            node,
            now=current,
            stale_after_seconds=stale_after_seconds,
        )
        for node in nodes
    ]

    online = sum(item.effective_connectivity == "online" for item in statuses)
    stale = sum(item.effective_connectivity == "stale" for item in statuses)
    offline = sum(
        item.effective_connectivity in {"offline", "disabled"}
        for item in statuses
    )
    installing = sum(
        item.installation_status in ACTIVE_INSTALL_STATUSES
        for item in statuses
    )
    successful = sum(
        item.installation_status in SUCCESS_STATUSES
        for item in statuses
    )
    failed = sum(
        item.installation_status in FAILURE_STATUSES
        for item in statuses
    )
    attention = sum(item.support_attention for item in statuses)

    if failed:
        health = "failed"
    elif attention:
        health = "attention"
    elif not statuses:
        health = "empty"
    elif installing:
        health = "installing"
    elif online == len(statuses):
        health = "healthy"
    else:
        health = "degraded"

    return DeploymentOperationsSummary(
        profile_id=profile.id,
        profile_name=profile.name,
        purpose=profile.purpose,
        total_nodes=len(statuses),
        online_nodes=online,
        stale_nodes=stale,
        offline_nodes=offline,
        installing_nodes=installing,
        successful_nodes=successful,
        failed_nodes=failed,
        attention_nodes=attention,
        health=health,
        nodes=statuses,
    )


def get_deployment_operations_summary(
    db: Session,
    profile: DeploymentProfile,
    *,
    stale_after_seconds: int = 300,
) -> DeploymentOperationsSummary:
    nodes = list(
        db.scalars(
            select(Node)
            .where(Node.deployment_profile_id == profile.id)
            .order_by(Node.name)
        ).unique()
    )
    return build_deployment_operations_summary(
        profile,
        nodes,
        stale_after_seconds=stale_after_seconds,
    )
