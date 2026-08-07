from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.services.deployment_operations_service import (
    build_deployment_operations_summary,
    effective_connectivity,
)


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def make_node(
    *,
    name="node-1",
    last_seen_at=NOW,
    connectivity_state="online",
    lifecycle_state="approved",
    installation_status="success",
    failure_category="",
):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        lifecycle_state=lifecycle_state,
        connectivity_state=connectivity_state,
        last_seen_at=last_seen_at,
        installation_status=installation_status,
        installation_stage="health_checks",
        installation_failure_category=failure_category,
        installation_message="sanitized operational message",
        installation_updated_at=NOW,
    )


def make_profile():
    return SimpleNamespace(
        id=uuid4(),
        name="GPU Deployment",
        purpose="gpu_compute",
    )


def test_recent_node_is_effectively_online():
    node = make_node()
    assert effective_connectivity(
        node,
        now=NOW,
        stale_after_seconds=300,
    ) == "online"


def test_old_heartbeat_is_stale():
    node = make_node(last_seen_at=NOW - timedelta(minutes=10))
    assert effective_connectivity(
        node,
        now=NOW,
        stale_after_seconds=300,
    ) == "stale"


def test_failed_installation_requires_support_attention():
    node = make_node(
        installation_status="failed",
        failure_category="health_check_failed",
    )
    summary = build_deployment_operations_summary(
        make_profile(),
        [node],
        now=NOW,
    )
    assert summary.health == "failed"
    assert summary.failed_nodes == 1
    assert summary.attention_nodes == 1
    assert summary.nodes[0].support_reason == "health_check_failed"


def test_stale_node_requires_support_attention():
    node = make_node(last_seen_at=NOW - timedelta(minutes=10))
    summary = build_deployment_operations_summary(
        make_profile(),
        [node],
        now=NOW,
    )
    assert summary.health == "attention"
    assert summary.stale_nodes == 1
    assert summary.nodes[0].support_reason == "node_stale"


def test_all_online_successful_nodes_are_healthy():
    nodes = [
        make_node(name="node-1"),
        make_node(name="node-2"),
    ]
    summary = build_deployment_operations_summary(
        make_profile(),
        nodes,
        now=NOW,
    )
    assert summary.health == "healthy"
    assert summary.total_nodes == 2
    assert summary.online_nodes == 2
    assert summary.successful_nodes == 2
    assert summary.attention_nodes == 0


def test_empty_deployment_is_explicit():
    summary = build_deployment_operations_summary(
        make_profile(),
        [],
        now=NOW,
    )
    assert summary.health == "empty"
    assert summary.total_nodes == 0
