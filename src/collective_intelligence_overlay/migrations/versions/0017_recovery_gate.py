"""Persist restored intake closure independently of process restart."""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"


def upgrade() -> None:
    op.add_column(
        "feed_state",
        sa.Column("restore_pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("feed_state", sa.Column("restored_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("feed_state", "restored_at")
    op.drop_column("feed_state", "restore_pending")
