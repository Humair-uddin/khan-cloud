"""secure VPS provisioning foundation

Revision ID: b72e4d5f6a61
Revises: a61d2c3e4f50
Create Date: 2026-08-08
"""
from typing import Sequence, Union
import uuid
from alembic import op
import sqlalchemy as sa

revision: str = "b72e4d5f6a61"
down_revision: Union[str, Sequence[str], None] = "a61d2c3e4f50"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provisioning_authorizations",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="authorized"),
        sa.Column("reference_type", sa.String(length=50), nullable=False, server_default=""),
        sa.Column("reference_id", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("organization_id","created_by_user_id","source","status"):
        op.create_index(f"ix_provisioning_authorizations_{col}", "provisioning_authorizations", [col])

    op.add_column("vps_instances", sa.Column("provisioning_authorization_id", sa.UUID(), nullable=True))
    op.add_column("vps_instances", sa.Column("access_username", sa.String(length=64), nullable=False, server_default="ubuntu"))
    op.add_column("vps_instances", sa.Column("ssh_public_key_fingerprint", sa.String(length=128), nullable=False, server_default=""))
    op.add_column("vps_instances", sa.Column("guest_ready_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT DISTINCT organization_id, created_by_user_id FROM vps_instances"
    )).fetchall()
    for org_id, user_id in rows:
        auth_id = str(uuid.uuid4())
        bind.execute(sa.text(
            "INSERT INTO provisioning_authorizations "
            "(id,organization_id,created_by_user_id,source,status,reference_type,reference_id,created_at,updated_at) "
            "VALUES (:id,:org,:usr,'migration','consumed','historical','pre-authorization-vps',now(),now())"
        ), {"id": auth_id, "org": org_id, "usr": user_id})
        bind.execute(sa.text(
            "UPDATE vps_instances SET provisioning_authorization_id=:auth "
            "WHERE organization_id=:org AND provisioning_authorization_id IS NULL"
        ), {"auth": auth_id, "org": org_id})

    op.alter_column("vps_instances", "provisioning_authorization_id", nullable=False)
    op.create_foreign_key(
        "fk_vps_instances_provisioning_authorization",
        "vps_instances", "provisioning_authorizations",
        ["provisioning_authorization_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index(
        "ix_vps_instances_provisioning_authorization_id",
        "vps_instances", ["provisioning_authorization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_vps_instances_provisioning_authorization_id", table_name="vps_instances")
    op.drop_constraint("fk_vps_instances_provisioning_authorization", "vps_instances", type_="foreignkey")
    op.drop_column("vps_instances", "guest_ready_at")
    op.drop_column("vps_instances", "ssh_public_key_fingerprint")
    op.drop_column("vps_instances", "access_username")
    op.drop_column("vps_instances", "provisioning_authorization_id")
    op.drop_table("provisioning_authorizations")
