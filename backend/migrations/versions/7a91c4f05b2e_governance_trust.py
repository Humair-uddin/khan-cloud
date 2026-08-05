"""governance trust
Revision ID: 7a91c4f05b2e
Revises: cc41a40d7f22
Create Date: 2026-08-05
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str="7a91c4f05b2e"
down_revision: Union[str,Sequence[str],None]="cc41a40d7f22"
branch_labels=None
depends_on=None

def upgrade() -> None:
    op.add_column("nodes",sa.Column("lifecycle_state",sa.String(30),nullable=False,server_default="pending_approval"))
    op.add_column("nodes",sa.Column("connectivity_state",sa.String(30),nullable=False,server_default="unknown"))
    op.add_column("nodes",sa.Column("marketplace_state",sa.String(30),nullable=False,server_default="not_eligible"))
    op.add_column("nodes",sa.Column("capabilities",postgresql.JSONB(astext_type=sa.Text()),nullable=False,server_default=sa.text("'{}'::jsonb")))
    op.create_index("ix_nodes_lifecycle_state","nodes",["lifecycle_state"])
    op.create_index("ix_nodes_connectivity_state","nodes",["connectivity_state"])
    op.create_index("ix_nodes_marketplace_state","nodes",["marketplace_state"])
    op.execute("""
    UPDATE nodes SET
      lifecycle_state = CASE
        WHEN status='online' THEN 'approved'
        WHEN status IN ('disabled','rejected','retired','maintenance') THEN status
        ELSE 'pending_approval' END,
      connectivity_state = CASE WHEN status='online' THEN 'online' ELSE 'unknown' END
    """)
    op.create_table(
      "audit_events",
      sa.Column("actor_user_id",sa.UUID(),nullable=True),
      sa.Column("action",sa.String(150),nullable=False),
      sa.Column("resource_type",sa.String(100),nullable=False),
      sa.Column("resource_id",sa.String(255),nullable=False),
      sa.Column("reason",sa.String(500),nullable=False),
      sa.Column("result",sa.String(30),nullable=False),
      sa.Column("details",postgresql.JSONB(astext_type=sa.Text()),nullable=False),
      sa.Column("id",sa.UUID(),nullable=False),
      sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),
      sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),
      sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_actor_user_id","audit_events",["actor_user_id"])
    op.create_index("ix_audit_events_action","audit_events",["action"])
    op.create_index("ix_audit_events_resource_type","audit_events",["resource_type"])
    op.create_index("ix_audit_events_resource_id","audit_events",["resource_id"])
    op.create_index("ix_audit_events_result","audit_events",["result"])

def downgrade() -> None:
    op.drop_index("ix_audit_events_result",table_name="audit_events")
    op.drop_index("ix_audit_events_resource_id",table_name="audit_events")
    op.drop_index("ix_audit_events_resource_type",table_name="audit_events")
    op.drop_index("ix_audit_events_action",table_name="audit_events")
    op.drop_index("ix_audit_events_actor_user_id",table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_nodes_marketplace_state",table_name="nodes")
    op.drop_index("ix_nodes_connectivity_state",table_name="nodes")
    op.drop_index("ix_nodes_lifecycle_state",table_name="nodes")
    op.drop_column("nodes","capabilities")
    op.drop_column("nodes","marketplace_state")
    op.drop_column("nodes","connectivity_state")
    op.drop_column("nodes","lifecycle_state")
