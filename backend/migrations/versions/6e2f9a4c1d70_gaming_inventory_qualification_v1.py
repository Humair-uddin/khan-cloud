"""gaming inventory qualification v1
Revision ID: 6e2f9a4c1d70
Revises: 5d8e7f1a2b30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "6e2f9a4c1d70"
down_revision = "5d8e7f1a2b30"
branch_labels = None
depends_on = None


def _basecols():
    return [sa.Column("id", sa.UUID(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)]


def upgrade():
    op.create_table("gaming_titles", sa.Column("slug", sa.String(120), nullable=False), sa.Column("name", sa.String(200), nullable=False), sa.Column("launcher", sa.String(40), nullable=False, server_default="steam"), sa.Column("launcher_app_id", sa.String(120), nullable=False, server_default=""), sa.Column("platform", sa.String(40), nullable=False, server_default="windows"), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("minimum_vram_mb", sa.Integer(), nullable=False, server_default="8192"), sa.Column("minimum_memory_mb", sa.Integer(), nullable=False, server_default="8192"), sa.Column("minimum_cpu_threads", sa.Integer(), nullable=False, server_default="4"), sa.Column("minimum_storage_mb", sa.Integer(), nullable=False, server_default="0"), sa.Column("streaming_backend", sa.String(40), nullable=False, server_default="sunshine"), sa.Column("qualification_policy_version", sa.String(40), nullable=False, server_default="kg001-v1"), sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), *_basecols(), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("slug", name="uq_gaming_titles_slug"))
    for col in ("slug", "name", "launcher", "launcher_app_id", "platform", "enabled"):
        op.create_index(f"ix_gaming_titles_{col}", "gaming_titles", [col])

    op.create_table("node_game_inventory", sa.Column("node_id", sa.UUID(), nullable=False), sa.Column("gaming_title_id", sa.UUID(), nullable=False), sa.Column("launcher", sa.String(40), nullable=False, server_default=""), sa.Column("launcher_app_id", sa.String(120), nullable=False, server_default=""), sa.Column("install_state", sa.String(30), nullable=False, server_default="absent"), sa.Column("install_path", sa.String(1000), nullable=False, server_default=""), sa.Column("build_id", sa.String(120), nullable=False, server_default=""), sa.Column("manifest_path", sa.String(1000), nullable=False, server_default=""), sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("raw_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), *_basecols(), sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["gaming_title_id"], ["gaming_titles.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("node_id", "gaming_title_id", name="uq_node_game_inventory_node_title"))
    for col in ("node_id", "gaming_title_id", "install_state", "observed_at"):
        op.create_index(f"ix_node_game_inventory_{col}", "node_game_inventory", [col])

    op.create_table("node_game_qualifications", sa.Column("node_id", sa.UUID(), nullable=False), sa.Column("gaming_title_id", sa.UUID(), nullable=False), sa.Column("qualified", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("reason_codes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("policy_version", sa.String(40), nullable=False, server_default="kg001-v1"), sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True), sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), *_basecols(), sa.ForeignKeyConstraint(["node_id"], ["nodes.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["gaming_title_id"], ["gaming_titles.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("node_id", "gaming_title_id", name="uq_node_game_qualification_node_title"))
    for col in ("node_id", "gaming_title_id", "qualified", "policy_version", "evaluated_at"):
        op.create_index(f"ix_node_game_qualifications_{col}", "node_game_qualifications", [col])

    op.add_column("gaming_sessions", sa.Column("gaming_title_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_gaming_sessions_gaming_title", "gaming_sessions", "gaming_titles", ["gaming_title_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_gaming_sessions_gaming_title_id", "gaming_sessions", ["gaming_title_id"])


def downgrade():
    op.drop_index("ix_gaming_sessions_gaming_title_id", table_name="gaming_sessions")
    op.drop_constraint("fk_gaming_sessions_gaming_title", "gaming_sessions", type_="foreignkey")
    op.drop_column("gaming_sessions", "gaming_title_id")
    op.drop_table("node_game_qualifications")
    op.drop_table("node_game_inventory")
    op.drop_table("gaming_titles")
