"""Finite current-resolution projection; old uncertain rows and signatures stay unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"


def upgrade() -> None:
    op.create_table(
        "invocation_resolutions",
        sa.Column("caller", sa.String(160), primary_key=True),
        sa.Column("invocation_id", sa.String(160), primary_key=True),
        sa.Column("owner", sa.String(160), nullable=False),
        sa.Column("invocation_context", sa.String(64), nullable=False, unique=True),
        sa.Column("receipt_id", sa.String(160), nullable=False),
        sa.Column("state_digest", sa.String(64), nullable=False),
        sa.Column("revisions", sa.JSON(), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("invocation_resolutions")
