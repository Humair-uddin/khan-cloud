"""VPS networking and IPAM foundation

Revision ID: c83f6e7a8b72
Revises: b72e4d5f6a61
Create Date: 2026-08-08
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c83f6e7a8b72"
down_revision: Union[str, Sequence[str], None] = "b72e4d5f6a61"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "network_pools",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("network_type", sa.String(length=30), nullable=False),
        sa.Column("cidr", sa.String(length=64), nullable=False),
        sa.Column("gateway", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("region", sa.String(length=80), nullable=False, server_default="pk-local"),
        sa.Column("dns_servers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("externally_routable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        sa.UniqueConstraint("cidr"),
    )
    for col in ("slug","network_type","region","is_active","is_default"):
        op.create_index(f"ix_network_pools_{col}", "network_pools", [col])

    op.create_table(
        "ip_allocations",
        sa.Column("pool_id", sa.UUID(), nullable=False),
        sa.Column("vps_instance_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("address", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("allocation_source", sa.String(length=40), nullable=False, server_default="hypervisor_dhcp"),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pool_id"], ["network_pools.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vps_instance_id"], ["vps_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pool_id", "address", name="uq_ip_allocation_pool_address"),
    )
    for col in ("pool_id","vps_instance_id","organization_id","address","status"):
        op.create_index(f"ix_ip_allocations_{col}", "ip_allocations", [col])

    pool_id = str(uuid.uuid4())
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO network_pools "
            "(id,name,slug,network_type,cidr,gateway,region,dns_servers,is_active,is_default,externally_routable,created_at,updated_at) "
            "VALUES (:id,:name,:slug,:network_type,:cidr,:gateway,:region,CAST(:dns_servers AS jsonb),"
            "true,true,false,now(),now())"
        ),
        {
            "id": pool_id,
            "name": "Khan Cloud VPS Private NAT",
            "slug": "kc-vps-private-nat",
            "network_type": "private_nat",
            "cidr": "192.168.250.0/24",
            "gateway": "192.168.250.1",
            "region": "pk-local",
            "dns_servers": '["1.1.1.1","1.0.0.1"]',
        },
    )

    # Backfill only currently live VPS addresses. Historical deleted VMs remain historical.
    rows = bind.execute(sa.text(
        "SELECT id,organization_id,primary_ip FROM vps_instances "
        "WHERE status <> 'deleted' AND primary_ip LIKE '192.168.250.%' AND primary_ip <> ''"
    )).fetchall()
    for vps_id, org_id, address in rows:
        bind.execute(sa.text(
            "INSERT INTO ip_allocations "
            "(id,pool_id,vps_instance_id,organization_id,address,status,allocation_source,allocated_at,created_at,updated_at) "
            "VALUES (:id,:pool,:vps,:org,:address,'active','migration',now(),now(),now()) "
            "ON CONFLICT (pool_id,address) DO NOTHING"
        ), {
            "id": str(uuid.uuid4()), "pool": pool_id, "vps": vps_id,
            "org": org_id, "address": address,
        })


def downgrade() -> None:
    op.drop_table("ip_allocations")
    op.drop_table("network_pools")
