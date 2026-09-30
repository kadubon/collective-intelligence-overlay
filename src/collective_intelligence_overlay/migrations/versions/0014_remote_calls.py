"""Persist new explicit remote call references; never reconstruct legacy identities."""

from alembic import op
from sqlalchemy import Column, DateTime, String

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.create_table(
        "remote_calls",
        Column("owner", String(160), primary_key=True),
        Column("caller", String(160), primary_key=True),
        Column("call_key", String(64), primary_key=True),
        Column("call_id", String(160), nullable=False),
        Column("call_scope", String(160), nullable=False),
        Column("parent_context", String(64)),
        Column("invocation_context", String(64)),
        Column("request_fingerprint", String(64), nullable=False),
        Column("lineage_fingerprint", String(64), nullable=False),
        Column("provider", String(160), nullable=False),
        Column("endpoint", String(2048), nullable=False),
        Column("binding_id", String(160), nullable=False),
        Column("binding_digest", String(64), nullable=False),
        Column("provider_binding_id", String(160), nullable=False),
        Column("provider_binding_digest", String(64), nullable=False),
        Column("remote_invocation_id", String(160), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_remote_invocation_context", "remote_calls", ["owner", "caller", "invocation_context"]
    )
    op.create_index("ix_remote_call_scope", "remote_calls", ["owner", "caller", "call_scope"])
    # 0.3.0 has no logical child IDs. Its invocation rows/UNKNOWNs stay untouched;
    # operators query the original provider ID rather than inventing a new mapping.


def downgrade() -> None:
    raise RuntimeError("restore a consistent backup; remote call references cannot be discarded")
