from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict

class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_user_id: UUID | None
    action: str
    resource_type: str
    resource_id: str
    reason: str
    result: str
    details: dict[str, Any]
    created_at: datetime
    updated_at: datetime
