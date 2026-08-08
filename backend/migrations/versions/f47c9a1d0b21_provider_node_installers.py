"""provider node installer artifacts

Revision ID: f47c9a1d0b21
Revises: e31a7c2d9f10
Create Date: 2026-08-08
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

revision: str = "f47c9a1d0b21"
down_revision: Union[str, Sequence[str], None] = "e31a7c2d9f10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "node_installer_artifacts",
        sa.Column("deployment_profile_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("node_name", sa.String(length=128), nullable=False),
        sa.Column("node_role", sa.String(length=40), nullable=False),
        sa.Column("filename", sa.String(length=200), nullable=False),
        sa.Column("artifact_path", sa.String(length=600), nullable=False),
        sa.Column("download_token_hash", sa.String(length=64), nullable=False),
        sa.Column("download_token_prefix", sa.String(length=12), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_downloads", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["deployment_profile_id"], ["deployment_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("download_token_hash"),
    )
    for column in ["deployment_profile_id","organization_id","created_by_user_id","node_name","node_role","download_token_hash","download_token_prefix","expires_at"]:
        op.create_index(f"ix_node_installer_artifacts_{column}", "node_installer_artifacts", [column])

    bind = op.get_bind()
    code = "node_installers.manage"
    permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar()
    if permission_id is None:
        permission_id = str(uuid.uuid4())
        bind.execute(sa.text("INSERT INTO permissions (id, code, description, created_at, updated_at) VALUES (:id,:code,:description,now(),now())"), {"id": permission_id, "code": code, "description": "Generate scoped node installers."})
    for role_name in ["platform_owner","platform_admin","operator","marketplace_manager","customer"]:
        role_id = bind.execute(sa.text("SELECT id FROM roles WHERE name=:name"), {"name": role_name}).scalar()
        if role_id is None:
            continue
        exists = bind.execute(sa.text("SELECT 1 FROM role_permissions WHERE role_id=:role AND permission_id=:permission"), {"role": role_id, "permission": permission_id}).scalar()
        if exists is None:
            bind.execute(sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role,:permission)"), {"role": role_id, "permission": permission_id})


def downgrade() -> None:
    op.drop_table("node_installer_artifacts")
