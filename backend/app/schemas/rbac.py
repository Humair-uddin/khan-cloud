from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    description: str


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    description: str = Field(default="", max_length=255)
    permissions: list[str] = []


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    permissions: list[PermissionRead]


class UserRoleAssignment(BaseModel):
    role_name: str = Field(min_length=2, max_length=100)


class CurrentAccess(BaseModel):
    roles: list[str]
    permissions: list[str]
    is_superuser: bool
