"""gaming connection leases v1

Revision ID: 9c5e3a7b14d2
Revises: 83a4f2d91c60
"""

from alembic import op
import sqlalchemy as sa


revision = "9c5e3a7b14d2"
down_revision = "83a4f2d91c60"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gaming_connection_leases",
        sa.Column("gaming_session_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column(
            "state",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "client_name",
            sa.String(100),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "sunshine_client_uuid",
            sa.String(160),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "pairing_expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "paired_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "failure_message",
            sa.String(500),
            nullable=False,
            server_default="",
        ),
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
        sa.ForeignKeyConstraint(
            ["gaming_session_id"],
            ["gaming_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["nodes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    for column in (
        "gaming_session_id",
        "organization_id",
        "user_id",
        "node_id",
        "state",
        "client_name",
        "sunshine_client_uuid",
        "pairing_expires_at",
    ):
        op.create_index(
            f"ix_gaming_connection_leases_{column}",
            "gaming_connection_leases",
            [column],
        )


def downgrade():
    op.drop_table("gaming_connection_leases")
