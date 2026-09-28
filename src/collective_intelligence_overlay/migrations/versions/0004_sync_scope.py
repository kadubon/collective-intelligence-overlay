"""Persist the subject scope of synchronization observations."""

from alembic import op
from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.add_column(
        "sync_checkpoints",
        Column("subjects", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    op.create_index("ix_sync_subjects", "sync_checkpoints", ["subjects"], postgresql_using="gin")


def downgrade() -> None:
    raise RuntimeError("restore consistent backup; freshness scope cannot be downgraded")
