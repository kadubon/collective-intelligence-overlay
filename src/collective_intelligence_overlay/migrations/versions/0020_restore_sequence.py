"""Retain the commit boundary before post-restore operational observations."""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"


def upgrade() -> None:
    # Existing restored generations have no positive boundary proof. Do not
    # invent one from today's sequence or rewrite their original records.
    op.add_column("feed_state", sa.Column("restored_sequence", sa.BigInteger()))


def downgrade() -> None:
    op.drop_column("feed_state", "restored_sequence")
