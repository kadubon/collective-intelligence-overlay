"""Bound owner-local active invocation inspection without rewriting history."""

from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.create_index("ix_invocations_owner_state", "invocations", ["owner", "state"])


def downgrade() -> None:
    op.drop_index("ix_invocations_owner_state", table_name="invocations")
