from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NodeOperationsStatus(BaseModel):
    node_id: UUID
    name: str
    lifecycle_state: str
    connectivity_state: str
    effective_connectivity: str
    last_seen_at: datetime | None
    installation_status: str
    installation_stage: str
    installation_failure_category: str
    installation_message: str
    installation_updated_at: datetime | None
    support_attention: bool
    support_reason: str


class DeploymentOperationsSummary(BaseModel):
    profile_id: UUID
    profile_name: str
    purpose: str
    total_nodes: int
    online_nodes: int
    stale_nodes: int
    offline_nodes: int
    installing_nodes: int
    successful_nodes: int
    failed_nodes: int
    attention_nodes: int
    health: str
    nodes: list[NodeOperationsStatus] = Field(default_factory=list)
