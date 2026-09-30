"""Order owner-local running candidates without rewriting authoritative rows."""

from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade() -> None:
    op.create_index(
        "ix_invocations_owner_running_order",
        "invocations",
        ["owner", "state", "created_at", "caller", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_invocations_owner_running_order", table_name="invocations")
