"""Index the most recent owner-local allocation choice for bounded cooldown lookup."""

from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade() -> None:
    op.create_index("ix_selection_owner_time", "work_selections", ["owner", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_selection_owner_time", table_name="work_selections")
