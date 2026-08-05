"""deployment profiles

Revision ID: b8f11a29e6d1
Revises: 7a91c4f05b2e
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b8f11a29e6d1"
down_revision: Union[str, Sequence[str], None] = "7a91c4f05b2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_profiles",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("ownership_type", sa.String(length=50), nullable=False),
        sa.Column("visibility", sa.String(length=50), nullable=False),
        sa.Column("control_plane_url", sa.String(length=500), nullable=False),
        sa.Column(
            "allowed_services",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "resource_policy",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("enrollment_code_hash", sa.String(length=64), nullable=False),
        sa.Column("enrollment_code_prefix", sa.String(length=12), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("uses_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
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
        "ix_deployment_profiles_name",
        "deployment_profiles",
        ["name"],
    )
    op.create_index(
        "ix_deployment_profiles_purpose",
        "deployment_profiles",
        ["purpose"],
    )
    op.create_index(
        "ix_deployment_profiles_ownership_type",
        "deployment_profiles",
        ["ownership_type"],
    )
    op.create_index(
        "ix_deployment_profiles_visibility",
        "deployment_profiles",
        ["visibility"],
    )
    op.create_index(
        "ix_deployment_profiles_enrollment_code_hash",
        "deployment_profiles",
        ["enrollment_code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_deployment_profiles_enrollment_code_prefix",
        "deployment_profiles",
        ["enrollment_code_prefix"],
    )
    op.create_index(
        "ix_deployment_profiles_created_by_user_id",
        "deployment_profiles",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_deployment_profiles_is_active",
        "deployment_profiles",
        ["is_active"],
    )

    op.add_column(
        "nodes",
        sa.Column("deployment_profile_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "nodes",
        sa.Column(
            "intended_purpose",
            sa.String(length=50),
            nullable=False,
            server_default="internal_lab",
        ),
    )
    op.create_index(
        "ix_nodes_deployment_profile_id",
        "nodes",
        ["deployment_profile_id"],
    )
    op.create_index(
        "ix_nodes_intended_purpose",
        "nodes",
        ["intended_purpose"],
    )


def downgrade() -> None:
    op.drop_index("ix_nodes_intended_purpose", table_name="nodes")
    op.drop_index("ix_nodes_deployment_profile_id", table_name="nodes")
    op.drop_column("nodes", "intended_purpose")
    op.drop_column("nodes", "deployment_profile_id")

    op.drop_index(
        "ix_deployment_profiles_is_active",
        table_name="deployment_profiles",
    )
    op.drop_index(
        "ix_deployment_profiles_created_by_user_id",
        table_name="deployment_profiles",
    )
    op.drop_index(
        "ix_deployment_profiles_enrollment_code_prefix",
        table_name="deployment_profiles",
    )
    op.drop_index(
        "ix_deployment_profiles_enrollment_code_hash",
        table_name="deployment_profiles",
    )
    op.drop_index(
        "ix_deployment_profiles_visibility",
        table_name="deployment_profiles",
    )
    op.drop_index(
        "ix_deployment_profiles_ownership_type",
        table_name="deployment_profiles",
    )
    op.drop_index(
        "ix_deployment_profiles_purpose",
        table_name="deployment_profiles",
    )
    op.drop_index(
        "ix_deployment_profiles_name",
        table_name="deployment_profiles",
    )
    op.drop_table("deployment_profiles")
