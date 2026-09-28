"""Track releasable invocation allowance without inventing old execution history."""

from alembic import op
from sqlalchemy import Column, String

revision = "0009"
down_revision = "0008"


def upgrade() -> None:
    # Stop all old workers before upgrade. Existing rows remain conservative even
    # when their old phase says reserved; the migration grants no refund authority.
    op.add_column(
        "invocations",
        Column("reservation_state", String(32), nullable=False, server_default="legacy_unknown"),
    )
    op.add_column("invocations", Column("release_reason", String(160), nullable=True))


def downgrade() -> None:
    raise RuntimeError("restore a consistent backup; allowance history cannot be discarded")
