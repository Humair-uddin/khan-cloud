"""physical host identity and redeployment lifecycle v1"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "5d8e7f1a2b30"
down_revision = "16d99df1a001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("physical_hosts",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("system_uuid", sa.String(255), nullable=False, server_default=""),
        sa.Column("serial_number", sa.String(255), nullable=False, server_default=""),
        sa.Column("manufacturer", sa.String(255), nullable=False, server_default=""),
        sa.Column("model", sa.String(255), nullable=False, server_default=""),
        sa.Column("trust_state", sa.String(30), nullable=False, server_default="observed"),
        sa.Column("deployment_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"],["organizations.id"],ondelete="SET NULL"),
        sa.UniqueConstraint("fingerprint"))
    for col in ("organization_id","fingerprint","system_uuid","serial_number","trust_state","last_seen_at"):
        op.create_index(f"ix_physical_hosts_{col}","physical_hosts",[col],unique=(col=="fingerprint"))
    op.add_column("nodes", sa.Column("physical_host_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("nodes", sa.Column("deployment_generation", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("nodes", sa.Column("superseded_by_node_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_nodes_physical_host_id","nodes","physical_hosts",["physical_host_id"],["id"],ondelete="SET NULL")
    op.create_foreign_key("fk_nodes_superseded_by_node_id","nodes","nodes",["superseded_by_node_id"],["id"],ondelete="SET NULL")
    op.create_index("ix_nodes_physical_host_id","nodes",["physical_host_id"])
    op.create_index("ix_nodes_superseded_by_node_id","nodes",["superseded_by_node_id"])

def downgrade():
    op.drop_index("ix_nodes_superseded_by_node_id",table_name="nodes"); op.drop_index("ix_nodes_physical_host_id",table_name="nodes")
    op.drop_constraint("fk_nodes_superseded_by_node_id","nodes",type_="foreignkey"); op.drop_constraint("fk_nodes_physical_host_id","nodes",type_="foreignkey")
    op.drop_column("nodes","superseded_by_node_id"); op.drop_column("nodes","deployment_generation"); op.drop_column("nodes","physical_host_id")
    op.drop_table("physical_hosts")
