"""compute capacity and VPS foundation

Revision ID: a61d2c3e4f50
Revises: f47c9a1d0b21
Create Date: 2026-08-08
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a61d2c3e4f50"
down_revision: Union[str, Sequence[str], None] = "f47c9a1d0b21"
branch_labels = None
depends_on = None


def _base_columns():
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "node_capacities",
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("cpu_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cpu_reserved_host", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cpu_allocatable", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cpu_allocated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("memory_total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("memory_reserved_host_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("memory_allocatable_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("memory_allocated_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("storage_total_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("storage_reserved_host_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("storage_allocatable_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("storage_allocated_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("kvm_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("libvirt_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("virtualization_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("execution_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("scheduling_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", name="uq_node_capacities_node_id"),
    )
    op.create_index("ix_node_capacities_node_id", "node_capacities", ["node_id"])
    op.create_index("ix_node_capacities_virtualization_ready", "node_capacities", ["virtualization_ready"])
    op.create_index("ix_node_capacities_execution_enabled", "node_capacities", ["execution_enabled"])
    op.create_index("ix_node_capacities_scheduling_enabled", "node_capacities", ["scheduling_enabled"])

    op.create_table(
        "vps_instances",
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("image", sa.String(length=100), nullable=False, server_default="ubuntu-24.04"),
        sa.Column("vcpu", sa.Integer(), nullable=False),
        sa.Column("memory_bytes", sa.BigInteger(), nullable=False),
        sa.Column("disk_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("desired_state", sa.String(length=40), nullable=False, server_default="running"),
        sa.Column("runtime_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("primary_ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("failure_category", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("failure_message", sa.String(length=500), nullable=False, server_default=""),
        *_base_columns(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ["organization_id", "node_id", "created_by_user_id", "name", "status"]:
        op.create_index(f"ix_vps_instances_{col}", "vps_instances", [col])

    op.create_table(
        "resource_reservations",
        sa.Column("vps_instance_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("cpu", sa.Integer(), nullable=False),
        sa.Column("memory_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="reserved"),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(["vps_instance_id"], ["vps_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vps_instance_id", name="uq_resource_reservation_vps"),
    )
    for col in ["vps_instance_id", "node_id", "status"]:
        op.create_index(f"ix_resource_reservations_{col}", "resource_reservations", [col])

    op.create_table(
        "node_jobs",
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("vps_instance_id", sa.UUID(), nullable=True),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("error_message", sa.String(length=500), nullable=False, server_default=""),
        *_base_columns(),
        sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vps_instance_id"], ["vps_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ["node_id", "vps_instance_id", "job_type", "status"]:
        op.create_index(f"ix_node_jobs_{col}", "node_jobs", [col])

    bind = op.get_bind()
    permissions = {
        "compute.hosts.read": "View compute host capacity.",
        "vps.read": "View VPS instances.",
        "vps.manage": "Create and manage VPS instances.",
    }
    for code, description in permissions.items():
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar()
        if permission_id is None:
            permission_id = str(uuid.uuid4())
            bind.execute(sa.text(
                "INSERT INTO permissions (id,code,description,created_at,updated_at) VALUES (:id,:code,:description,now(),now())"
            ), {"id": permission_id, "code": code, "description": description})

    role_map = {
        "platform_owner": set(permissions),
        "platform_admin": set(permissions),
        "operator": set(permissions),
        "customer": {"vps.read", "vps.manage"},
        "support_engineer": {"vps.read"},
    }
    for role_name, codes in role_map.items():
        role_id = bind.execute(sa.text("SELECT id FROM roles WHERE name=:name"), {"name": role_name}).scalar()
        if role_id is None:
            continue
        for code in codes:
            permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE code=:code"), {"code": code}).scalar()
            exists = bind.execute(sa.text(
                "SELECT 1 FROM role_permissions WHERE role_id=:role AND permission_id=:permission"
            ), {"role": role_id, "permission": permission_id}).scalar()
            if exists is None:
                bind.execute(sa.text(
                    "INSERT INTO role_permissions (role_id,permission_id) VALUES (:role,:permission)"
                ), {"role": role_id, "permission": permission_id})


def downgrade() -> None:
    op.drop_table("node_jobs")
    op.drop_table("resource_reservations")
    op.drop_table("vps_instances")
    op.drop_table("node_capacities")
