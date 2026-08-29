"""provider execution reliability v1

Revision ID: f2a002d10001
Revises: f2a002c10001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f2a002d10001"
down_revision = "f2a002c10001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_webhook_forensic_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "provider_code",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "payload_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "signature_fingerprint",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "outcome_code",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "http_status",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "retryable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "error_class",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "length(trim(provider_code)) > 0",
            name="ck_payment_forensic_provider_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(event_id)) > 0",
            name="ck_payment_forensic_event_nonempty",
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_payment_forensic_payload_hash",
        ),
        sa.CheckConstraint(
            "http_status >= 100 AND http_status <= 599",
            name="ck_payment_forensic_http_status",
        ),
    )

    op.create_index(
        "ix_payment_forensic_provider_event",
        "payment_webhook_forensic_events",
        ["provider_code", "event_id"],
    )

    op.create_index(
        "ix_payment_forensic_received_at",
        "payment_webhook_forensic_events",
        ["received_at"],
    )

    op.create_table(
        "payment_provider_health_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "provider_code",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "details_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "length(trim(provider_code)) > 0",
            name="ck_payment_health_provider_nonempty",
        ),
        sa.CheckConstraint(
            "status IN "
            "('healthy','degraded','unavailable','disabled','unknown')",
            name="ck_payment_health_status",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_payment_health_latency",
        ),
    )

    op.create_index(
        "ix_payment_health_provider_observed",
        "payment_provider_health_events",
        ["provider_code", "observed_at"],
    )

    op.create_table(
        "payment_financial_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "aggregate_type",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "aggregate_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "payload_json",
            postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "payload_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "locked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_payment_financial_outbox_idempotency",
        ),
        sa.CheckConstraint(
            "length(trim(event_type)) > 0",
            name="ck_payment_outbox_event_type_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(aggregate_type)) > 0",
            name="ck_payment_outbox_aggregate_type_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(aggregate_id)) > 0",
            name="ck_payment_outbox_aggregate_id_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(idempotency_key)) > 0",
            name="ck_payment_outbox_idempotency_nonempty",
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_payment_outbox_payload_hash",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','processed','failed')",
            name="ck_payment_outbox_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_payment_outbox_attempt_count",
        ),
    )

    op.create_index(
        "ix_payment_outbox_status_available",
        "payment_financial_outbox",
        ["status", "available_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_outbox_status_available",
        table_name="payment_financial_outbox",
    )

    op.drop_table(
        "payment_financial_outbox"
    )

    op.drop_index(
        "ix_payment_health_provider_observed",
        table_name="payment_provider_health_events",
    )

    op.drop_table(
        "payment_provider_health_events"
    )

    op.drop_index(
        "ix_payment_forensic_received_at",
        table_name="payment_webhook_forensic_events",
    )

    op.drop_index(
        "ix_payment_forensic_provider_event",
        table_name="payment_webhook_forensic_events",
    )

    op.drop_table(
        "payment_webhook_forensic_events"
    )
