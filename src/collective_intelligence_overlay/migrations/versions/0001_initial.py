"""Initial schema snapshot. Do not import evolving runtime metadata here."""

from alembic import op
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, Numeric, String, Table

revision = "0001"
down_revision = None

metadata = MetaData()
records = Table(
    "records",
    metadata,
    Column("kind", String(32), primary_key=True),
    Column("issuer", String(160), primary_key=True),
    Column("record_id", String(330), primary_key=True),
    Column("body", JSON, nullable=False),
    Column("envelope", JSON, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
)
decisions = Table(
    "decisions",
    metadata,
    Column("id", String(160), primary_key=True),
    Column("body", JSON, nullable=False),
)
leases = Table(
    "leases",
    metadata,
    Column("task_id", String(160), primary_key=True),
    Column("worker", String(160), nullable=False),
    Column("fence", Integer, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("state", String(16), nullable=False),
    Column("reservation", Numeric(24, 9), nullable=False),
    Column("unit", String(160), nullable=False),
    Column("actual", Numeric(24, 9), nullable=True),
)
budgets = Table(
    "budgets",
    metadata,
    Column("unit", String(160), primary_key=True),
    Column("remaining", Numeric(24, 9), nullable=False),
)
dependencies = Table(
    "dependencies",
    metadata,
    Column("parent", String(330), primary_key=True),
    Column("child", String(330), primary_key=True),
    Column("digest", String(64), nullable=False),
)


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("destructive downgrade unsupported; restore a verified backup")
