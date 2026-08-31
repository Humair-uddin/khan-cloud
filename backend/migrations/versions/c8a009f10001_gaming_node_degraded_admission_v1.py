"""gaming node degraded admission health v1"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="c8a009f10001"
down_revision="c6a009f10001"
branch_labels=None
depends_on=None
def upgrade():
    op.add_column("nodes",sa.Column("gaming_health_state",sa.String(32),nullable=False,server_default="healthy"))
    op.add_column("nodes",sa.Column("gaming_health_reasons",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")))
    op.add_column("nodes",sa.Column("gaming_health_degraded_at",sa.DateTime(timezone=True),nullable=True))
    op.add_column("nodes",sa.Column("gaming_health_recovered_at",sa.DateTime(timezone=True),nullable=True))
    op.add_column("nodes",sa.Column("gaming_admission_auto_blocked",sa.Boolean(),nullable=False,server_default=sa.false()))
    op.create_index("ix_nodes_gaming_health_state","nodes",["gaming_health_state"])
    op.alter_column("nodes","gaming_health_state",server_default=None)
    op.alter_column("nodes","gaming_health_reasons",server_default=None)
    op.alter_column("nodes","gaming_admission_auto_blocked",server_default=None)
def downgrade():
    op.drop_index("ix_nodes_gaming_health_state",table_name="nodes")
    op.drop_column("nodes","gaming_admission_auto_blocked")
    op.drop_column("nodes","gaming_health_recovered_at")
    op.drop_column("nodes","gaming_health_degraded_at")
    op.drop_column("nodes","gaming_health_reasons")
    op.drop_column("nodes","gaming_health_state")
