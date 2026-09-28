"""Receiver-owned synchronization checkpoints; no business payload changes."""

from alembic import op
from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, Text

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.create_table(
        "sync_checkpoints",
        Column("source", String(160), primary_key=True),
        Column("filter_digest", String(64), primary_key=True),
        Column("generation", String(64), nullable=True),
        Column("through", BigInteger, nullable=False),
        Column("upper", BigInteger, nullable=False),
        Column("anchor", DateTime(timezone=True), nullable=True),
        Column("cursor", Text, nullable=True),
        Column("complete", Boolean, nullable=False),
        Column("last_receipt", String(64), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError(
        "restore a consistent backup; synchronization checkpoints cannot be downgraded"
    )
