"""customer deployment association and support workflow

Revision ID: e31a7c2d9f10
Revises: d12f0a8e32c1
Create Date: 2026-08-08
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

revision: str = "e31a7c2d9f10"
down_revision: Union[str, Sequence[str], None] = "d12f0a8e32c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
    op.create_index("ix_organizations_created_by_user_id", "organizations", ["created_by_user_id"])
    op.create_index("ix_organizations_is_active", "organizations", ["is_active"])

    op.create_table(
        "organization_memberships",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False, server_default="member"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_membership"),
    )
    op.create_index("ix_org_memberships_org", "organization_memberships", ["organization_id"])
    op.create_index("ix_org_memberships_user", "organization_memberships", ["user_id"])

    op.add_column("deployment_profiles", sa.Column("organization_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_deployment_profiles_organization", "deployment_profiles", "organizations", ["organization_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_deployment_profiles_organization_id", "deployment_profiles", ["organization_id"])

    op.create_table(
        "support_cases",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("deployment_profile_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="normal"),
        sa.Column("category", sa.String(length=60), nullable=False, server_default="general"),
        sa.Column("summary", sa.String(length=250), nullable=False),
        sa.Column("sanitized_details", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("assigned_user_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deployment_profile_id"], ["deployment_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["organization_id", "deployment_profile_id", "node_id", "status", "priority", "category", "created_by_user_id", "assigned_user_id"]:
        op.create_index(f"ix_support_cases_{column}", "support_cases", [column])

    bind = op.get_bind()
    permissions = {
        "organizations.read": "View organizations.",
        "organizations.manage": "Manage organizations and memberships.",
        "support.read": "View support cases.",
        "support.manage": "Create and manage support cases.",
    }
    for code, description in permissions.items():
        existing = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar()
        if existing is None:
            bind.execute(sa.text("INSERT INTO permissions (id, code, description, created_at, updated_at) VALUES (:id, :code, :description, now(), now())"), {"id": str(uuid.uuid4()), "code": code, "description": description})

    role_map = {
        "platform_owner": set(permissions),
        "platform_admin": set(permissions),
        "operator": {"organizations.read", "support.read", "support.manage"},
        "support_engineer": {"organizations.read", "support.read", "support.manage"},
        "customer": {"organizations.read", "support.read", "support.manage"},
        "viewer": {"organizations.read", "support.read"},
    }
    for role_name, codes in role_map.items():
        role_id = bind.execute(sa.text("SELECT id FROM roles WHERE name=:name"), {"name": role_name}).scalar()
        if role_id is None:
            continue
        for code in codes:
            permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar()
            if permission_id is None:
                continue
            exists = bind.execute(sa.text("SELECT 1 FROM role_permissions WHERE role_id=:role_id AND permission_id=:permission_id"), {"role_id": role_id, "permission_id": permission_id}).scalar()
            if exists is None:
                bind.execute(sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)"), {"role_id": role_id, "permission_id": permission_id})


def downgrade() -> None:
    op.drop_table("support_cases")
    op.drop_index("ix_deployment_profiles_organization_id", table_name="deployment_profiles")
    op.drop_constraint("fk_deployment_profiles_organization", "deployment_profiles", type_="foreignkey")
    op.drop_column("deployment_profiles", "organization_id")
    op.drop_table("organization_memberships")
    op.drop_table("organizations")
