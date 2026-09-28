"""Persistent business invocations refer to existing leases and budgets."""

from alembic import op
from sqlalchemy import JSON, Column, DateTime, Integer, String

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.create_table(
        "invocations",
        Column("caller", String(160), primary_key=True),
        Column("id", String(160), primary_key=True),
        Column("owner", String(160), nullable=False),
        Column("fingerprint", String(64), nullable=False),
        Column("binding_id", String(160), nullable=False),
        Column("binding_digest", String(64), nullable=False),
        Column("request", JSON, nullable=False),
        Column("lease_id", String(160), nullable=False, unique=True),
        Column("worker", String(160), nullable=False),
        Column("fence", Integer, nullable=False),
        Column("state", String(32), nullable=False),
        Column("phase", String(32), nullable=False),
        Column("result", JSON, nullable=True),
        Column("result_digest", String(64), nullable=True),
        Column("reason", String(160), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_invocation_binding", "invocations", ["binding_id", "binding_digest", "created_at"]
    )


def downgrade() -> None:
    raise RuntimeError("restore consistent backup; invocation outcomes cannot be discarded")
