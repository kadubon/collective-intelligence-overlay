"""Local DB completion time is distinct from a source-declared freshness anchor."""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"


def upgrade() -> None:
    op.add_column("sync_checkpoints", sa.Column("completed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("sync_checkpoints", "completed_at")
