from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DashboardCounts(BaseModel):
    organizations: int = 0
    deployments: int = 0
    nodes: int = 0
    online_nodes: int = 0
    stale_nodes: int = 0
    offline_nodes: int = 0
    installing_nodes: int = 0
    successful_nodes: int = 0
    failed_nodes: int = 0
    attention_nodes: int = 0
    open_support_cases: int = 0
    urgent_support_cases: int = 0


class DashboardDeployment(BaseModel):
    profile_id: UUID
    organization_id: UUID | None
    profile_name: str
    purpose: str
    health: str
    total_nodes: int
    online_nodes: int
    stale_nodes: int
    offline_nodes: int
    failed_nodes: int
    attention_nodes: int


class DashboardAttentionItem(BaseModel):
    kind: str
    organization_id: UUID | None
    deployment_profile_id: UUID
    node_id: UUID | None = None
    support_case_id: UUID | None = None
    priority: str
    reason: str
    summary: str
    occurred_at: datetime | None = None


class OperationsDashboard(BaseModel):
    generated_at: datetime
    counts: DashboardCounts
    deployments: list[DashboardDeployment] = Field(default_factory=list)
    attention_queue: list[DashboardAttentionItem] = Field(default_factory=list)
