"""Public gateway and port mappings.

Revision ID: c75f8d75b793
Revises: d94a7f8b9c83
Create Date: 2026-08-09

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c75f8d75b793"
down_revision: Union[str, Sequence[str], None] = "d94a7f8b9c83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_gateways",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("public_ip", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("region", sa.String(length=80), nullable=False),
        sa.Column("gateway_type", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_public_gateways_gateway_type",
        "public_gateways",
        ["gateway_type"],
        unique=False,
    )
    op.create_index(
        "ix_public_gateways_is_active",
        "public_gateways",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        "ix_public_gateways_public_ip",
        "public_gateways",
        ["public_ip"],
        unique=True,
    )
    op.create_index(
        "ix_public_gateways_region",
        "public_gateways",
        ["region"],
        unique=False,
    )
    op.create_index(
        "ix_public_gateways_slug",
        "public_gateways",
        ["slug"],
        unique=True,
    )

    op.create_table(
        "port_mappings",
        sa.Column("gateway_id", sa.UUID(), nullable=False),
        sa.Column("vps_instance_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("protocol", sa.String(length=10), nullable=False),
        sa.Column("public_port", sa.Integer(), nullable=False),
        sa.Column("private_ip", sa.String(length=64), nullable=False),
        sa.Column("private_port", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("allocation_source", sa.String(length=40), nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "protocol IN ('tcp', 'udp')",
            name="ck_port_mapping_protocol",
        ),
        sa.CheckConstraint(
            "private_port BETWEEN 1 AND 65535",
            name="ck_port_mapping_private_port",
        ),
        sa.CheckConstraint(
            "public_port BETWEEN 1 AND 65535",
            name="ck_port_mapping_public_port",
        ),
        sa.ForeignKeyConstraint(
            ["gateway_id"],
            ["public_gateways.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vps_instance_id"],
            ["vps_instances.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_port_mappings_gateway_id",
        "port_mappings",
        ["gateway_id"],
        unique=False,
    )
    op.create_index(
        "ix_port_mappings_organization_id",
        "port_mappings",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_port_mappings_protocol",
        "port_mappings",
        ["protocol"],
        unique=False,
    )
    op.create_index(
        "ix_port_mappings_public_port",
        "port_mappings",
        ["public_port"],
        unique=False,
    )
    op.create_index(
        "ix_port_mappings_status",
        "port_mappings",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_port_mappings_vps_instance_id",
        "port_mappings",
        ["vps_instance_id"],
        unique=False,
    )

    op.create_index(
        "uq_port_mapping_active_endpoint",
        "port_mappings",
        ["gateway_id", "protocol", "public_port"],
        unique=True,
        postgresql_where=sa.text("status <> 'released'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_port_mapping_active_endpoint",
        table_name="port_mappings",
        postgresql_where=sa.text("status <> 'released'"),
    )

    op.drop_index(
        "ix_port_mappings_vps_instance_id",
        table_name="port_mappings",
    )
    op.drop_index(
        "ix_port_mappings_status",
        table_name="port_mappings",
    )
    op.drop_index(
        "ix_port_mappings_public_port",
        table_name="port_mappings",
    )
    op.drop_index(
        "ix_port_mappings_protocol",
        table_name="port_mappings",
    )
    op.drop_index(
        "ix_port_mappings_organization_id",
        table_name="port_mappings",
    )
    op.drop_index(
        "ix_port_mappings_gateway_id",
        table_name="port_mappings",
    )

    op.drop_table("port_mappings")

    op.drop_index(
        "ix_public_gateways_slug",
        table_name="public_gateways",
    )
    op.drop_index(
        "ix_public_gateways_region",
        table_name="public_gateways",
    )
    op.drop_index(
        "ix_public_gateways_public_ip",
        table_name="public_gateways",
    )
    op.drop_index(
        "ix_public_gateways_is_active",
        table_name="public_gateways",
    )
    op.drop_index(
        "ix_public_gateways_gateway_type",
        table_name="public_gateways",
    )

    op.drop_table("public_gateways")
