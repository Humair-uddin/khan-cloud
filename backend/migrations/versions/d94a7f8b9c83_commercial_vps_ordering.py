"""commercial VPS ordering foundation
Revision ID: d94a7f8b9c83
Revises: c83f6e7a8b72
"""
from typing import Sequence,Union
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="d94a7f8b9c83"; down_revision="c83f6e7a8b72"; branch_labels=None; depends_on=None

def basecols():
    return [
      sa.Column("id",sa.UUID(),nullable=False),
      sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),
      sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.text("now()"),nullable=False),
    ]

def upgrade():
    op.create_table("product_catalog_items",
      sa.Column("code",sa.String(80),nullable=False),sa.Column("workload_type",sa.String(40),nullable=False),sa.Column("name",sa.String(120),nullable=False),
      sa.Column("description",sa.String(500),nullable=False,server_default=""),sa.Column("currency",sa.String(3),nullable=False,server_default="PKR"),
      sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("is_sellable",sa.Boolean(),nullable=False,server_default=sa.false()),
      sa.Column("metadata_json",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),*basecols(),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("code"))
    op.create_table("product_rates",
      sa.Column("product_id",sa.UUID(),nullable=False),sa.Column("dimension",sa.String(60),nullable=False),sa.Column("unit",sa.String(30),nullable=False),
      sa.Column("unit_price_minor",sa.BigInteger(),nullable=False),sa.Column("minimum_units",sa.Integer(),nullable=False,server_default="0"),sa.Column("maximum_units",sa.Integer(),nullable=False,server_default="0"),
      sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()),*basecols(),sa.ForeignKeyConstraint(["product_id"],["product_catalog_items.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"))
    op.create_table("commercial_quotes",
      sa.Column("organization_id",sa.UUID(),nullable=False),sa.Column("user_id",sa.UUID(),nullable=False),sa.Column("product_id",sa.UUID(),nullable=False),
      sa.Column("currency",sa.String(3),nullable=False),sa.Column("billing_period",sa.String(20),nullable=False),sa.Column("amount_minor",sa.BigInteger(),nullable=False),
      sa.Column("configuration",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),sa.Column("pricing_snapshot",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
      sa.Column("status",sa.String(30),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),*basecols(),
      sa.ForeignKeyConstraint(["organization_id"],["organizations.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["product_id"],["product_catalog_items.id"],ondelete="RESTRICT"),sa.PrimaryKeyConstraint("id"))
    op.create_table("customer_orders",
      sa.Column("organization_id",sa.UUID(),nullable=False),sa.Column("user_id",sa.UUID(),nullable=False),sa.Column("quote_id",sa.UUID(),nullable=False),sa.Column("product_id",sa.UUID(),nullable=False),
      sa.Column("currency",sa.String(3),nullable=False),sa.Column("amount_minor",sa.BigInteger(),nullable=False),sa.Column("status",sa.String(40),nullable=False),sa.Column("payment_status",sa.String(40),nullable=False),sa.Column("payment_method",sa.String(60),nullable=False),
      sa.Column("configuration",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),sa.Column("pricing_snapshot",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
      sa.Column("provisioning_authorization_id",sa.UUID(),nullable=True),sa.Column("vps_instance_id",sa.UUID(),nullable=True),sa.Column("paid_at",sa.DateTime(timezone=True),nullable=True),sa.Column("provisioning_started_at",sa.DateTime(timezone=True),nullable=True),*basecols(),
      sa.ForeignKeyConstraint(["organization_id"],["organizations.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["user_id"],["users.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["quote_id"],["commercial_quotes.id"],ondelete="RESTRICT"),
      sa.ForeignKeyConstraint(["product_id"],["product_catalog_items.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["provisioning_authorization_id"],["provisioning_authorizations.id"],ondelete="RESTRICT"),sa.ForeignKeyConstraint(["vps_instance_id"],["vps_instances.id"],ondelete="SET NULL"),sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("quote_id"))
    op.create_table("payment_attempts",
      sa.Column("order_id",sa.UUID(),nullable=False),sa.Column("method",sa.String(60),nullable=False),sa.Column("status",sa.String(40),nullable=False),sa.Column("amount_minor",sa.BigInteger(),nullable=False),sa.Column("currency",sa.String(3),nullable=False),
      sa.Column("provider_reference",sa.String(160),nullable=False,server_default=""),sa.Column("evidence_reference",sa.String(255),nullable=False,server_default=""),sa.Column("confirmed_by_user_id",sa.UUID(),nullable=True),sa.Column("confirmed_at",sa.DateTime(timezone=True),nullable=True),*basecols(),
      sa.ForeignKeyConstraint(["order_id"],["customer_orders.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["confirmed_by_user_id"],["users.id"],ondelete="RESTRICT"),sa.PrimaryKeyConstraint("id"))
    p=str(uuid.uuid4())
    op.get_bind().execute(sa.text("INSERT INTO product_catalog_items (id,code,workload_type,name,description,currency,is_active,is_sellable,metadata_json,created_at,updated_at) VALUES (:id,'vps-configurable','vps','Configurable VPS','Khan Cloud configurable virtual private server.','PKR',true,false,CAST(:m AS jsonb),now(),now())"),{"id":p,"m":'{"network_tiers":["shared_gateway"],"images":["ubuntu-24.04"],"dedicated_ipv4_future":true}'})

def downgrade():
    for t in ("payment_attempts","customer_orders","commercial_quotes","product_rates","product_catalog_items"): op.drop_table(t)
