"""Persist owner-local choices; invocation state remains in the existing executor."""

from alembic import op
from sqlalchemy import JSON, Column, DateTime, String

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.create_table(
        "work_selections",
        Column("owner", String(160), primary_key=True),
        Column("opportunity_id", String(160), primary_key=True),
        Column("body", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("restore a consistent backup; durable choices cannot be discarded")
