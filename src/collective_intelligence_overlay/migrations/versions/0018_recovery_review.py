"""Reference an operator-reviewed recovery observation, without a second ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"


def upgrade() -> None:
    op.add_column("feed_state", sa.Column("recovery_receipt", sa.String(160)))
    op.add_column("feed_state", sa.Column("recovery_digest", sa.String(64)))


def downgrade() -> None:
    op.drop_column("feed_state", "recovery_digest")
    op.drop_column("feed_state", "recovery_receipt")
