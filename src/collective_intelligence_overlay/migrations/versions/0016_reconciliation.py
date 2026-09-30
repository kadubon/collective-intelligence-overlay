"""Retain exact remote arguments for new calls; legacy mappings stay unknown."""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"


def upgrade() -> None:
    op.add_column("remote_calls", sa.Column("arguments_digest", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("remote_calls", "arguments_digest")
