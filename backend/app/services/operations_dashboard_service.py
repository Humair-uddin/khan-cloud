from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deployment_profile import DeploymentProfile
from app.models.node import Node
from app.models.organization import Organization
from app.models.support_case import SupportCase
from app.models.user import User
from app.schemas.operations_dashboard import (
    DashboardAttentionItem,
    DashboardCounts,
    DashboardDeployment,
    OperationsDashboard,
)
from app.services.deployment_operations_service import (
    build_deployment_operations_summary,
)
from app.services.organization_service import (
    user_can_access_organization,
    user_can_access_deployment_profile,
    visible_organizations,
)


OPEN_CASE_STATUSES = {"open", "in_progress", "waiting"}
URGENT_PRIORITIES = {"urgent", "critical"}


def build_operations_dashboard(
    db: Session,
    user: User,
    *,
    stale_after_seconds: int = 300,
) -> OperationsDashboard:
    if stale_after_seconds < 30 or stale_after_seconds > 86400:
        raise ValueError("stale_after_seconds must be between 30 and 86400.")

    now = datetime.now(UTC)
    organizations = visible_organizations(db, user)
    organization_ids = {item.id for item in organizations}

    profiles = [
        profile
        for profile in db.scalars(
            select(DeploymentProfile).order_by(DeploymentProfile.name)
        ).unique()
        if user_can_access_deployment_profile(db, user, profile)
    ]

    nodes = list(db.scalars(select(Node).order_by(Node.name)).unique())
    nodes_by_profile: dict = {}
    for node in nodes:
        if node.deployment_profile_id is not None:
            nodes_by_profile.setdefault(node.deployment_profile_id, []).append(node)

    dashboard_deployments: list[DashboardDeployment] = []
    attention: list[DashboardAttentionItem] = []

    total_nodes = online = stale = offline = installing = successful = failed = attention_nodes = 0

    for profile in profiles:
        summary = build_deployment_operations_summary(
            profile,
            nodes_by_profile.get(profile.id, []),
            now=now,
            stale_after_seconds=stale_after_seconds,
        )
        dashboard_deployments.append(
            DashboardDeployment(
                profile_id=profile.id,
                organization_id=profile.organization_id,
                profile_name=profile.name,
                purpose=profile.purpose,
                health=summary.health,
                total_nodes=summary.total_nodes,
                online_nodes=summary.online_nodes,
                stale_nodes=summary.stale_nodes,
                offline_nodes=summary.offline_nodes,
                failed_nodes=summary.failed_nodes,
                attention_nodes=summary.attention_nodes,
            )
        )
        total_nodes += summary.total_nodes
        online += summary.online_nodes
        stale += summary.stale_nodes
        offline += summary.offline_nodes
        installing += summary.installing_nodes
        successful += summary.successful_nodes
        failed += summary.failed_nodes
        attention_nodes += summary.attention_nodes

        for item in summary.nodes:
            if item.support_attention:
                attention.append(
                    DashboardAttentionItem(
                        kind="node",
                        organization_id=profile.organization_id,
                        deployment_profile_id=profile.id,
                        node_id=item.node_id,
                        priority="high" if item.installation_status in {"failed", "rollback_failed"} else "normal",
                        reason=item.support_reason,
                        summary=f"{profile.name} / {item.name}",
                        occurred_at=item.installation_updated_at or item.last_seen_at,
                    )
                )

    cases = [
        case
        for case in db.scalars(
            select(SupportCase).order_by(SupportCase.created_at.desc())
        ).unique()
        if user_can_access_organization(db, user, case.organization_id)
    ]
    open_cases = [case for case in cases if case.status in OPEN_CASE_STATUSES]

    for case in open_cases:
        attention.append(
            DashboardAttentionItem(
                kind="support_case",
                organization_id=case.organization_id,
                deployment_profile_id=case.deployment_profile_id,
                node_id=case.node_id,
                support_case_id=case.id,
                priority=case.priority,
                reason=case.category,
                summary=case.summary,
                occurred_at=case.created_at,
            )
        )

    priority_rank = {"critical": 0, "urgent": 1, "high": 2, "normal": 3, "low": 4}
    attention.sort(
        key=lambda item: (
            priority_rank.get(item.priority, 3),
            -(item.occurred_at.timestamp() if item.occurred_at else 0),
        )
    )

    return OperationsDashboard(
        generated_at=now,
        counts=DashboardCounts(
            organizations=len(organizations),
            deployments=len(profiles),
            nodes=total_nodes,
            online_nodes=online,
            stale_nodes=stale,
            offline_nodes=offline,
            installing_nodes=installing,
            successful_nodes=successful,
            failed_nodes=failed,
            attention_nodes=attention_nodes,
            open_support_cases=len(open_cases),
            urgent_support_cases=sum(case.priority in URGENT_PRIORITIES for case in open_cases),
        ),
        deployments=dashboard_deployments,
        attention_queue=attention[:100],
    )
