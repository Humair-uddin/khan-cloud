"""RAW-E2E-39 gaming billing availability cutoff.

Revision ID: e39000100001
Revises: c8a009f10001
"""

from alembic import op
import sqlalchemy as sa

revision = "e39000100001"
down_revision = "c8a009f10001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gaming_sessions",
        sa.Column(
            "availability_cutoff_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "gaming_sessions",
        sa.Column(
            "availability_interrupted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "gaming_sessions",
        "availability_interrupted_at",
    )
    op.drop_column(
        "gaming_sessions",
        "availability_cutoff_at",
    )
