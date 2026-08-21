"""gaming windows vm orchestration v1

Revision ID: b7d5c1a92f40
Revises: 9c5e3a7b14d2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b7d5c1a92f40"
down_revision = "9c5e3a7b14d2"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "gaming_vm_blueprints",
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("template_vmid", sa.Integer(), nullable=False),
        sa.Column("storage", sa.String(80), nullable=False, server_default="local-lvm"),
        sa.Column("bridge", sa.String(80), nullable=False, server_default="vmbr0"),
        sa.Column("machine", sa.String(40), nullable=False, server_default="q35"),
        sa.Column("bios", sa.String(20), nullable=False, server_default="ovmf"),
        sa.Column("bootstrap_mode", sa.String(50), nullable=False, server_default="prebaked_agent_qga"),
        sa.Column("reset_policy", sa.String(40), nullable=False, server_default="destroy_on_terminate"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_gaming_vm_blueprints_slug"),
    )
    op.create_index("ix_gaming_vm_blueprints_slug", "gaming_vm_blueprints", ["slug"])
    op.create_index("ix_gaming_vm_blueprints_enabled", "gaming_vm_blueprints", ["enabled"])
    op.add_column("gaming_sessions", sa.Column("guest_node_id", sa.UUID(), nullable=True))
    op.add_column("gaming_sessions", sa.Column("deployment_mode", sa.String(40), nullable=False, server_default="bare_metal"))
    op.add_column("gaming_sessions", sa.Column("deployment_blueprint_id", sa.UUID(), nullable=True))
    op.add_column("gaming_sessions", sa.Column("guest_vm_id", sa.Integer(), nullable=True))
    op.add_column("gaming_sessions", sa.Column("deployment_stage", sa.String(60), nullable=False, server_default=""))
    op.create_foreign_key("fk_gaming_sessions_guest_node", "gaming_sessions", "nodes", ["guest_node_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_gaming_sessions_vm_blueprint", "gaming_sessions", "gaming_vm_blueprints", ["deployment_blueprint_id"], ["id"], ondelete="SET NULL")
    for col in ("guest_node_id","deployment_mode","deployment_blueprint_id","guest_vm_id","deployment_stage"):
        op.create_index(f"ix_gaming_sessions_{col}", "gaming_sessions", [col])

    # The server defaults above exist only to make the migration safe for
    # existing rows. Runtime defaults are application/ORM responsibilities.
    op.alter_column(
        "gaming_sessions",
        "deployment_mode",
        server_default=None,
    )
    op.alter_column(
        "gaming_sessions",
        "deployment_stage",
        server_default=None,
    )

    for col in (
        "enabled",
        "storage",
        "bridge",
        "machine",
        "bios",
        "bootstrap_mode",
        "reset_policy",
        "metadata_json",
    ):
        op.alter_column(
            "gaming_vm_blueprints",
            col,
            server_default=None,
        )

def downgrade():
    for col in ("deployment_stage","guest_vm_id","deployment_blueprint_id","deployment_mode","guest_node_id"):
        op.drop_index(f"ix_gaming_sessions_{col}", table_name="gaming_sessions")
    op.drop_constraint("fk_gaming_sessions_vm_blueprint", "gaming_sessions", type_="foreignkey")
    op.drop_constraint("fk_gaming_sessions_guest_node", "gaming_sessions", type_="foreignkey")
    for col in ("deployment_stage","guest_vm_id","deployment_blueprint_id","deployment_mode","guest_node_id"):
        op.drop_column("gaming_sessions", col)
    op.drop_index("ix_gaming_vm_blueprints_enabled", table_name="gaming_vm_blueprints")
    op.drop_index("ix_gaming_vm_blueprints_slug", table_name="gaming_vm_blueprints")
    op.drop_table("gaming_vm_blueprints")
